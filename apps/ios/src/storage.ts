import type { SQLiteDatabase } from 'expo-sqlite';
import { encode, normalize } from './normalize';
import type { LocationObject } from 'expo-location';
import type { Diagnostic, GpsEvent, Identity, Summary, Trip, TransportMode } from './types';
export type ActiveTrip = { trip_id: string; labels: Array<{ at: number; mode: TransportMode | null }>; stop_at?: number; error?: string };
export type Delivery = { event_id: string; payload: string; endpoint: string; retry_count: number; lease_token: string };
export const DDL = `
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trips (trip_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(trip_id), sequence INTEGER NOT NULL CHECK(sequence>=1), payload TEXT NOT NULL, saved_at TEXT NOT NULL, UNIQUE(trip_id,sequence));
CREATE TABLE IF NOT EXISTS diagnostics (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT REFERENCES trips(trip_id), payload TEXT NOT NULL);
-- Disable the old automatic send queue without deleting any recorded GPS.
DROP TRIGGER IF EXISTS gps_outbox_insert;
CREATE TABLE IF NOT EXISTS active_trip (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trip_sync (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gps_delivery (
 event_id TEXT PRIMARY KEY REFERENCES events(event_id), endpoint TEXT,
 send_status TEXT NOT NULL DEFAULT 'pending', retry_count INTEGER NOT NULL DEFAULT 0,
 retry_at REAL NOT NULL DEFAULT 0, last_error TEXT, sent_at TEXT,
 lease_until REAL NOT NULL DEFAULT 0, lease_token TEXT);
CREATE TRIGGER IF NOT EXISTS gps_delivery_insert AFTER INSERT ON events BEGIN
 INSERT INTO gps_delivery(event_id) VALUES (NEW.event_id);
END;
PRAGMA user_version = 6;`;
export class Storage {
  private tail: Promise<unknown> = Promise.resolve();
  constructor(private db: SQLiteDatabase) {}
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const result = this.tail.then(fn); this.tail = result.catch(() => {}); return result;
  }
  async init(uuid: () => string, now: string): Promise<Identity> {
    await this.db.execAsync(DDL);
    await this.db.runAsync('INSERT OR IGNORE INTO identity VALUES (1, ?)', encode({ user_id: uuid(), device_id: uuid() }));
    const active = await this.active();
    for (const trip of await this.list()) if (trip.status === 'recording' && trip.trip_id !== active?.trip_id) {
      const { gps_count: _count, first_event_time: _first, last_event_time: _last, last_saved_at: _saved, latest: _latest, ...metadata } = trip;
      await this.saveTrip({ ...metadata, status: 'interrupted', interruption_reason: 'process_restarted', recovered_at: now });
      await this.diagnostic(trip.trip_id, { recorded_at: now, kind: 'recovery', detail: '이전 실행의 종료 확인 불가' });
    }
    return this.identity();
  }
  async identity(): Promise<Identity> {
    const row=await this.db.getFirstAsync<{payload:string}>('SELECT payload FROM identity WHERE singleton=1');
    return JSON.parse(row!.payload);
  }
  saveTrip(trip: Trip) { return this.transaction(async () => {
    await this.db.runAsync('INSERT INTO trips VALUES (?, ?) ON CONFLICT(trip_id) DO UPDATE SET payload=excluded.payload', trip.trip_id, encode(trip));
    if (trip.server) await this.db.runAsync("DELETE FROM trip_sync WHERE key='start' AND json_extract(payload,'$.request_id')=?",trip.server.request_id);
  }); }
  async syncValue<T>(key: string): Promise<T | null> {
    const row=await this.db.getFirstAsync<{payload:string}>('SELECT payload FROM trip_sync WHERE key=?',key);
    return row ? JSON.parse(row.payload) : null;
  }
  saveSync(key: string, value: unknown) {
    return this.serial(()=>this.db.runAsync('INSERT INTO trip_sync VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',key,encode(value)));
  }
  async list(): Promise<Summary[]> {
    const rows = await this.db.getAllAsync<{ trip_id: string }>('SELECT trip_id FROM trips ORDER BY rowid DESC');
    return Promise.all(rows.map(r => this.summary(r.trip_id)));
  }
  async summary(id: string): Promise<Summary> {
    const row = await this.db.getFirstAsync<{ payload: string }>('SELECT payload FROM trips WHERE trip_id=?', id);
    if (!row) throw new Error('Trip 없음');
    const count = await this.db.getFirstAsync<{ n: number }>('SELECT COUNT(*) n FROM events WHERE trip_id=?', id);
    const first = await this.db.getFirstAsync<{ payload: string }>('SELECT payload FROM events WHERE trip_id=? ORDER BY sequence LIMIT 1', id);
    const last = await this.db.getFirstAsync<{ payload: string; saved_at: string }>('SELECT payload,saved_at FROM events WHERE trip_id=? ORDER BY sequence DESC LIMIT 1', id);
    return { ...JSON.parse(row.payload), gps_count: count!.n, first_event_time: first ? JSON.parse(first.payload).event_time : null,
      last_event_time: last ? JSON.parse(last.payload).event_time : null, last_saved_at: last?.saved_at ?? null, latest: last ? JSON.parse(last.payload) : null };
  }
  insert(event: GpsEvent, savedAt: string) { return this.serial(() => this.db.runAsync('INSERT INTO events VALUES (?, ?, ?, ?, ?)', event.event_id, event.trip_id, event.sequence, encode(event), savedAt)); }
  diagnostic(id: string | null, d: Diagnostic) { return this.serial(() => this.db.runAsync('INSERT INTO diagnostics(trip_id,payload) VALUES (?, ?)', id, encode(d))); }
  async diagnostics(id: string): Promise<Diagnostic[]> {
    const rows = await this.db.getAllAsync<{ payload: string }>('SELECT payload FROM diagnostics WHERE trip_id=? ORDER BY id', id);
    return rows.map(r => JSON.parse(r.payload));
  }
  async *events(id: string): AsyncGenerator<string> {
    for await (const row of this.db.getEachAsync<{ payload: string }>('SELECT payload FROM events WHERE trip_id=? ORDER BY sequence', id)) yield row.payload;
  }
  async eventPage(id: string, after: number, limit: number): Promise<GpsEvent[]> {
    const rows = await this.db.getAllAsync<{ payload: string }>('SELECT payload FROM events WHERE trip_id=? AND sequence>? ORDER BY sequence LIMIT ?', id, after, limit);
    return rows.map(r => JSON.parse(r.payload));
  }
  private transaction<T>(fn: () => Promise<T>) {
    return this.serial(async () => {
      await this.db.execAsync('BEGIN IMMEDIATE');
      try { const result = await fn(); await this.db.execAsync('COMMIT'); return result; }
      catch(e) { await this.db.execAsync('ROLLBACK'); throw e; }
    });
  }
  async active(): Promise<ActiveTrip | null> {
    const row = await this.db.getFirstAsync<{payload:string}>('SELECT payload FROM active_trip WHERE singleton=1');
    return row ? JSON.parse(row.payload) : null;
  }
  startActive(trip: Trip, mode: TransportMode | null) {
    return this.transaction(async () => {
      if (await this.active()) throw new Error('이미 측정 중인 Trip이 있습니다.');
      await this.db.runAsync('INSERT INTO trips VALUES (?,?)', trip.trip_id, encode(trip));
      await this.db.runAsync('INSERT INTO active_trip VALUES (1,?)', encode({trip_id:trip.trip_id,labels:[{at:Date.parse(trip.started_at),mode}]}));
      if(trip.server) await this.db.runAsync("DELETE FROM trip_sync WHERE key='start' AND json_extract(payload,'$.request_id')=?",trip.server.request_id);
    });
  }
  changeLabel(id: string, mode: TransportMode, at: number) {
    return this.transaction(async () => {
      const active = await this.active();
      if (!active || active.trip_id !== id || active.stop_at !== undefined) return;
      active.labels.push({at,mode});
      await this.db.runAsync('UPDATE active_trip SET payload=? WHERE singleton=1',encode(active));
    });
  }
  setActiveError(error: string) {
    return this.transaction(async () => {
      const active = await this.active(); if (!active) return;
      active.error = error;
      await this.db.runAsync('UPDATE active_trip SET payload=? WHERE singleton=1', encode(active));
    });
  }
  markStopping(at: number) {
    return this.transaction(async () => {
      const active = await this.active(); if (!active) return;
      active.stop_at ??= at;
      await this.db.runAsync('UPDATE active_trip SET payload=? WHERE singleton=1',encode(active));
    });
  }
  finishActive(now: string, reason: string | null = null) {
    return this.transaction(async () => {
      const active = await this.active(); if (!active) return;
      const row = await this.db.getFirstAsync<{payload:string}>('SELECT payload FROM trips WHERE trip_id=?',active.trip_id);
      const trip: Trip = JSON.parse(row!.payload);
      trip.status = reason ? 'interrupted' : 'completed';
      trip.ended_at = reason ? null : new Date(active.stop_at ?? Date.parse(now)).toISOString();
      trip.interruption_reason = reason;
      await this.db.runAsync('UPDATE trips SET payload=? WHERE trip_id=?',encode(trip),trip.trip_id);
      await this.db.runAsync('DELETE FROM active_trip WHERE singleton=1');
      return trip;
    });
  }
  appendBackground(locations: LocationObject[], received: string, uuid: () => string) {
    return this.transaction(async () => {
      const active = await this.active(); if (!active) return 0;
      const summary = await this.summary(active.trip_id);
      let previous = summary.latest, sequence = previous?.sequence ?? 0, count = 0;
      for (const raw of locations) {
        // Never attach a delayed fix from the previous Trip to a new Trip.
        if (Number.isFinite(raw.timestamp) && (raw.timestamp < Date.parse(summary.started_at) || (active.stop_at !== undefined && raw.timestamp > active.stop_at))) continue;
        let event: GpsEvent;
        const mode=[...active.labels].reverse().find(x=>x.at<=raw.timestamp)?.mode ?? active.labels[0].mode;
        try { event = normalize(raw,summary,sequence+1,uuid(),received,previous,mode); }
        catch(e) {
          await this.db.runAsync('INSERT INTO diagnostics(trip_id,payload) VALUES (?,?)',active.trip_id,encode({recorded_at:received,kind:'invalid_location',detail:{reason:String(e),raw_location:raw}}));
          continue;
        }
        event.source = 'expo-location.background';
        await this.db.runAsync('INSERT INTO events VALUES (?,?,?,?,?)',event.event_id,event.trip_id,event.sequence,encode(event),received);
        previous = event; sequence++; count++;
      }
      return count;
    });
  }
  claimDelivery(endpoint: string, now: number, token: string) {
    return this.transaction(async (): Promise<Delivery | null> => {
      await this.db.runAsync('UPDATE gps_delivery SET endpoint=? WHERE endpoint IS NULL',endpoint);
      const row = await this.db.getFirstAsync<Delivery & {retry_at:number;lease_until:number;send_status:string}>(
        `SELECT d.*,e.payload FROM gps_delivery d JOIN events e USING(event_id)
         WHERE d.endpoint=? AND d.send_status!='sent' ORDER BY e.rowid LIMIT 1`,endpoint);
      if (!row || row.send_status==='blocked' || row.retry_at>now || row.lease_until>now) return null;
      await this.db.runAsync('UPDATE gps_delivery SET lease_until=?,lease_token=? WHERE event_id=?',now+60000,token,row.event_id);
      return {...row,lease_token:token};
    });
  }
  deliverySuccess(job: Delivery, now: string) {
    return this.serial(()=>this.db.runAsync("UPDATE gps_delivery SET send_status='sent',sent_at=?,last_error=NULL,lease_until=0,lease_token=NULL WHERE event_id=? AND lease_token=?",now,job.event_id,job.lease_token));
  }
  deliveryFailure(job: Delivery, retryAt: number, error: string, blocked: boolean) {
    return this.serial(()=>this.db.runAsync('UPDATE gps_delivery SET send_status=?,retry_count=retry_count+1,retry_at=?,last_error=?,lease_until=0,lease_token=NULL WHERE event_id=? AND lease_token=?',blocked?'blocked':'pending',retryAt,error,job.event_id,job.lease_token));
  }
  retryDelivery() {
    return this.serial(()=>this.db.runAsync("UPDATE gps_delivery SET send_status='pending',retry_at=0,last_error=NULL WHERE send_status!='sent' AND lease_until=0"));
  }
  wakeDelivery() {
    return this.serial(()=>this.db.runAsync("UPDATE gps_delivery SET retry_at=0 WHERE send_status='pending'"));
  }
  async deliveryStatus(tripId: string | null = null) {
    return (await this.db.getFirstAsync<{pending:number;blocked:number;sent:number;last_success:string|null}>(
      `SELECT COALESCE(SUM(send_status!='sent'),0) pending,COALESCE(SUM(send_status='blocked'),0) blocked,
       COALESCE(SUM(send_status='sent'),0) sent,MAX(sent_at) last_success FROM gps_delivery
       WHERE (? IS NULL OR event_id IN (SELECT event_id FROM events WHERE trip_id=?))`,tripId,tripId))!;
  }
  async deliveryEvidence(tripId: string | null = null) {
    const sent = await this.db.getFirstAsync<{payload:string}>(
      `SELECT e.payload FROM gps_delivery d JOIN events e USING(event_id)
       WHERE d.send_status='sent' AND (? IS NULL OR e.trip_id=?) ORDER BY d.sent_at DESC,e.rowid DESC LIMIT 1`,tripId,tripId);
    const head = await this.db.getFirstAsync<{event_id:string;retry_count:number;last_error:string|null}>(
      `SELECT d.event_id,d.retry_count,d.last_error FROM gps_delivery d JOIN events e USING(event_id)
       WHERE d.send_status!='sent' AND (? IS NULL OR e.trip_id=?) ORDER BY e.rowid LIMIT 1`,tripId,tripId);
    return {sent:sent ? JSON.parse(sent.payload) as GpsEvent : null,head};
  }
  tripReport(tripId: string) {
    return this.transaction(async () => {
      const trip = await this.summary(tripId);
      const rows = await this.db.getAllAsync<{payload:string;send_status:string|null;sent_at:string|null;retry_count:number|null;last_error:string|null}>(
        `SELECT e.payload,d.send_status,d.sent_at,d.retry_count,d.last_error FROM events e
         LEFT JOIN gps_delivery d USING(event_id) WHERE e.trip_id=? ORDER BY e.sequence`,tripId);
      const events = rows.map(r=>({event:JSON.parse(r.payload) as GpsEvent,
        delivery:{status:r.send_status??'not_queued',accepted_at:r.sent_at,retry_count:r.retry_count??0,error:r.last_error}}));
      return {format:'canopy.gps.trip-check.v1',created_at:new Date().toISOString(),trip,
        checks:{collection:trip.status==='completed' && events.length>0,
          sequence:events.length>0 && events.every((r,i)=>r.event.sequence===i+1 && r.event.trip_id===tripId),
          api:events.length>0 && events.every(r=>r.delivery.status==='sent'),
          event_hubs:'unverified',raw:'unverified',device_fault_tests:'unverified'},events};
    });
  }
}
