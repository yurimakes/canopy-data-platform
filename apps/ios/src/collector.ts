import type { LocationObject } from 'expo-location';
import { normalize } from './normalize';
import { SCHEMA, MODES, currentMode, type TransportMode, type GpsEvent, type Identity, type Trip } from './types';
import type { Storage } from './storage';
export type CollectorPorts = {
  startTrip(identity: Identity): Promise<Pick<Trip,'trip_id'|'user_id'|'started_at'|'server'>>;
  permission(): Promise<void>;
  watch?(cb: (l: LocationObject) => void, error: (s: string) => void): Promise<{ remove(): void }>;
  background?: {start(): Promise<void>; stop(): Promise<void>; isRunning(): Promise<boolean>};
  awake(on: boolean): Promise<void>; uuid(): string; now(): string;
  settings: Record<string, unknown>; environment: Record<string, unknown>;
};
export class Collector {
  phase: 'idle' | 'starting' | 'recording' | 'stopping' | 'error' = 'idle';
  error = ''; trip: Trip | null = null; count = 0; latest: GpsEvent | null = null;
  lastReceived: string | null = null; appState = 'active';
  foregroundNotice = '';
  backgroundRunning = false;
  mode: TransportMode | null = null;
  private labels: Array<{ at: number; mode: TransportMode }> = [];
  private subscription?: { remove(): void };
  private accepting = false; private pending = 0; private queue = Promise.resolve();
  private starting?: Promise<void>; private stopping?: Promise<void>;
  private stopRequested = false; private fault: string | null = null;
  private stopAt?: number;
  private revision=0;
  constructor(private db: Storage, private identity: Identity, private p: CollectorPorts, public changed = () => {}) {}
  async selectMode(mode: TransportMode) {
    if (!MODES.some(m => m.value === mode)) throw new Error('지원하지 않는 이동수단');
    if (this.phase === 'starting' || this.phase === 'stopping' || this.mode === mode) return;
    if (this.p.background && this.trip?.status === 'recording') await this.db.changeLabel(this.trip.trip_id,mode,Date.parse(this.p.now()));
    this.mode = mode;
    if (this.phase === 'recording') this.labels.push({ at: Date.parse(this.p.now()), mode });
    this.changed();
  }
  start(): Promise<void> {
    if (this.phase === 'starting') return this.starting!;
    if (this.phase === 'recording' || this.phase === 'stopping') return Promise.resolve();
    if (this.trip?.status === 'recording') return Promise.resolve();
    if (!this.mode) { this.error = '이동수단을 먼저 선택하세요.'; this.changed(); return Promise.resolve(); }
    this.labels = [{ at: -Infinity, mode: this.mode }];
    this.revision++;
    this.phase = 'starting'; this.error = ''; this.fault = null; this.stopRequested = false; this.stopAt=undefined;
    this.trip = null; this.count = 0; this.latest = null; this.lastReceived = null; this.foregroundNotice = ''; this.changed();
    this.starting = this.begin(); return this.starting;
  }
  private async begin() {
    try {
      await this.p.permission();
      if (this.stopRequested) { this.phase = 'idle'; return; }
      const remote = await this.p.startTrip(this.identity);
      const trip: Trip = { ...this.identity, ...remote, schema_version: SCHEMA,
        ended_at: null, status: 'recording', interruption_reason: null, recovered_at: null, foreground_only: !this.p.background,
        collection_settings: this.p.settings, environment: this.p.environment };
      if (this.p.background) await this.db.startActive(trip,this.mode!);
      else await this.db.saveTrip(trip);
      this.trip = trip;
      await this.db.diagnostic(trip.trip_id, { recorded_at: this.p.now(), kind: 'permission_granted', detail: 'foreground' });
      if (this.p.background) {
        await this.p.background.start(); this.backgroundRunning = true;
        if (!this.stopRequested) this.phase = 'recording';
        return;
      }
      await this.p.awake(true);
      this.accepting = !this.stopRequested;
      this.subscription = await this.p.watch!(raw => this.receive(trip, raw), reason => {
        if (this.trip !== trip || !this.accepting) return;
        this.fail(`위치 수집 오류: ${reason}`);
      });
      if (!this.stopRequested && !this.fault) this.phase = 'recording';
    } catch (e) {
      this.fault = String(e); this.error = this.fault;
      try { await this.db.diagnostic(this.trip?.trip_id ?? null, { recorded_at: this.p.now(), kind: 'start_error', detail: this.error }); } catch { this.error += ' / 진단 저장 실패'; }
    } finally {
      this.changed();
      if (this.fault || this.stopRequested) void this.stop();
    }
  }
  private receive(trip: Trip, raw: LocationObject) {
    if (!this.accepting || this.trip !== trip) return;
    this.lastReceived = this.p.now(); this.changed();
    if (this.pending >= 256) { this.fail('저장 대기열 한도 초과: 수집 중단, 일부 수신 데이터 미저장'); return; }
    const received = this.lastReceived;
    // Use the GPS measurement timestamp, including delayed callbacks. Snapshot
    // before the asynchronous save so a button change cannot relabel queued GPS.
    const label = [...this.labels].reverse().find(x => x.at <= raw.timestamp)?.mode ?? this.mode!;
    this.enqueue(async () => {
      let event: GpsEvent;
      try { event = normalize(raw, trip, this.count + 1, this.p.uuid(), received, this.latest, label); }
      catch (e) { await this.db.diagnostic(trip.trip_id, { recorded_at: received, kind: 'invalid_location', detail: { reason: String(e), raw_location: raw } }); return; }
      await this.db.insert(event, this.p.now());
      this.count++; this.latest = event; this.changed();
    });
  }
  private enqueue(fn: () => Promise<void>) {
    this.pending++;
    this.queue = this.queue.then(fn).catch(e => this.fail(`저장 오류: ${String(e)} (미저장 이벤트 발생)`))
      .finally(() => { this.pending--; });
  }
  private fail(reason: string) {
    this.fault ??= reason; this.error = this.fault; this.accepting = false;
    this.subscription?.remove(); this.subscription = undefined; this.changed();
    void this.stop();
  }
  stop(): Promise<void> {
    this.revision++;
    this.stopAt ??= Date.parse(this.p.now());
    this.stopRequested = true; this.accepting = false;
    if (this.stopping) return this.stopping;
    if (this.phase === 'idle' || (this.phase === 'error' && !this.trip)) return Promise.resolve();
    this.phase = 'stopping'; this.changed();
    this.stopping = this.finish().finally(() => { this.stopping = undefined; }); return this.stopping;
  }
  private async finish() {
    // begin() never awaits stop(): subscription setup must settle before removal.
    await this.starting;
    if (this.p.background) {
      try {
        await this.db.markStopping(this.stopAt!);
        await this.p.background.stop(); this.backgroundRunning = false;
        const final = await this.db.finishActive(this.p.now(),this.fault);
        if (final) { this.trip=final; const summary=await this.db.summary(final.trip_id); this.count=summary.gps_count; this.latest=summary.latest; }
        this.phase=this.fault?'error':'idle';
      } catch(e) { this.phase='error'; this.error='GPS 종료 실패. 종료 버튼을 다시 눌러주세요: '+String(e); }
      this.changed(); return;
    }
    this.subscription?.remove(); this.subscription = undefined;
    await this.queue;
    try {
      if (this.trip) {
        const final: Trip = { ...this.trip, status: this.fault ? 'interrupted' : 'completed',
          ended_at: this.fault ? null : new Date(this.stopAt!).toISOString(), interruption_reason: this.fault };
        await this.db.diagnostic(final.trip_id, { recorded_at: this.p.now(), kind: 'collection_end', detail: { reason: this.fault, saved_count: this.count } });
        await this.db.saveTrip(final); this.trip = final;
        this.count = (await this.db.summary(final.trip_id)).gps_count;
      }
      this.phase = this.fault ? 'error' : 'idle';
    } catch (e) { this.phase = 'error'; this.error = `종료 저장 실패: ${String(e)}. 재시작 시 중단 기록으로 복구됩니다.`; }
    finally { try { await this.p.awake(false); } catch (e) { this.error += ` 화면 잠금 해제 오류: ${String(e)}`; } this.changed(); }
  }
  appStateChanged(state: string) {
    this.appState = state; this.changed();
    if (this.p.background) {
      if (state==='active') void this.refresh().catch(e=>{this.error=String(e);this.changed();});
      return;
    }
    if (!this.trip || !this.accepting) return;
    const id = this.trip.trip_id, now = this.p.now();
    this.foregroundNotice = `${now}: 앱 상태 ${state}. 앱 전환·잠금 중 관측 공백이 있을 수 있습니다.`;
    this.enqueue(async () => { await this.db.diagnostic(id, { recorded_at: now, kind: 'app_state', detail: state }); });
    // watchPositionAsync is foreground-only. Retain exactly one subscription on return.
  }
  interrupt(reason: string): Promise<void> {
    // UI unmounts and screen locks must not terminate a native background Trip.
    if (this.p.background) return Promise.resolve();
    if (this.phase === 'idle' || this.phase === 'error') return Promise.resolve();
    this.fault ??= reason; this.error = this.fault; return this.stop();
  }
  async refresh() {
    if (!this.p.background || this.phase==='starting' || this.phase==='stopping') return;
    const revision=this.revision;
    const active = await this.db.active();
    const running = await this.p.background.isRunning();
    // A user action may have started while the native query was in flight.
    if (revision!==this.revision || ['starting','stopping'].includes(this.phase)) return;
    this.backgroundRunning=running;
    if (!active) { if(running) {await this.p.background.stop();this.backgroundRunning=false;} return; }
    const summary=await this.db.summary(active.trip_id);
    if (revision!==this.revision || ['starting','stopping'].includes(this.phase)) return;
    this.trip=summary;this.count=summary.gps_count;this.latest=summary.latest;
    this.lastReceived=summary.latest?.received_at??null;this.mode=currentMode(active.labels.at(-1)!.mode);
    if (active.stop_at!==undefined) {await this.stop();return;}
    this.phase=running?'recording':'error';
    this.error=active.error || (running?'':'백그라운드 위치 수집이 꺼져 있습니다. 같은 Trip 재개 또는 측정 종료를 선택하세요.');
    this.changed();
  }
  async resume() {
    if (!this.p.background || this.phase==='starting' || this.phase==='stopping') return;
    this.revision++;this.phase='starting';this.changed();
    try {
      const active=await this.db.active(); if(!active || active.stop_at!==undefined) throw new Error('재개할 Trip이 없습니다.');
      await this.p.permission();
      await this.p.background.start();this.backgroundRunning=true;
      await this.db.setActiveError('');
      await this.db.diagnostic(active.trip_id,{recorded_at:this.p.now(),kind:'background_resumed',detail:'수집 공백은 보충하지 않음'});
      this.error='';this.phase='recording';
    } catch(e) {this.phase='error';this.error=String(e);}
    this.changed();
  }
}
