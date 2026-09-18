import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MODES, currentMode, type TransportMode, type GpsEvent, type Summary } from '../types';
import type { FeedbackInput, ServerTrip } from '../tripApi';
import {TripResult} from './TripResult';
export type MeasurementProps = {
  collectionMode?: "user" | "developer"; onBack(): void;
  mode: TransportMode | null; phase: string; ready: boolean; count: number; duration: string;
  accuracy: number | null; latestLabel?: GpsEvent['label']; tripId?: string; error: string;
  onMode(mode: TransportMode): void; onStart(): void; onStop(): void;
  onExport(): void; canExport: boolean; sharing: boolean;
  active?: boolean; backgroundRunning?: boolean; lastReceived?: string|null; sequence?: number;
  pending?: number; lastSuccess?: string|null; uploadError?: string;
  onResume?():void; onSettings?():void; onRetry?():void;
  foregroundOnly?:boolean; eventId?:string; eventTime?:string; confirmedEvent?:GpsEvent;
  retryCount?:number; canShareEvent?:boolean; onShareEvent?():void;
  resultTrip?:Summary; sent?:number; blocked?:number; onShareCheck?():void;
  serverTrip?:ServerTrip;tripError?:string;onRetryTrip?():void;
  feedbackPending?:FeedbackInput;onFeedback(input:FeedbackInput):Promise<void>;
  onHistory?():void;
};
export function MeasurementScreen(p: MeasurementProps) {
  const busy = p.active || ['starting','recording','stopping'].includes(p.phase);
  const developer = p.collectionMode !== "user";
  const switching = p.phase === 'starting' || p.phase === 'stopping';
  return <SafeAreaView style={s.root}>
    <ScrollView contentContainerStyle={s.content}>
      <Pressable accessibilityRole="button" disabled={!!busy} onPress={p.onBack} style={busy&&s.disabled}><Text style={s.modeText}>← 서비스 화면</Text></Pressable>
      <Text style={s.title}>{developer?'개발자 GPS 데이터 수집':'나의 이동 기록'}</Text>
      {!busy && <Pressable accessibilityRole="button" onPress={p.onHistory}><Text style={s.modeText}>이전 이동 결과 보기</Text></Pressable>}
      {!developer && <Text style={s.note}>이동을 시작할 때 시작 버튼을 누르고, 도착하면 종료하세요.</Text>}
      {developer && <>
      <Text style={s.note}>이동수단을 선택한 뒤 측정을 시작하세요.</Text>
      <View style={s.modes}>{MODES.map(m => <Pressable key={m.value} accessibilityRole="button"
        accessibilityState={{selected:p.mode === m.value, disabled: !p.ready || switching}}
        disabled={!p.ready || switching} onPress={() => p.onMode(m.value)} style={[s.mode, p.mode === m.value && s.selected]}>
        <Text style={[s.modeText, p.mode === m.value && s.selectedText]}>{p.mode === m.value ? '✓ ' : ''}{m.title}</Text>
      </Pressable>)}</View>
      <Text style={s.label}>선택 라벨: {MODES.find(m => m.value === p.mode)?.title ?? '선택 필요'}</Text>
      <Text style={s.note}>측정 중에도 변경할 수 있습니다. 변경 시각 이후 GPS부터 새 라벨로 저장됩니다.</Text>
      </>}
      <View style={s.card}>
        <Text style={s.status}>{p.phase === 'recording' ? '● 측정 중' : p.phase === 'starting' ? '측정 준비 중' : p.phase === 'stopping' ? '저장 마무리 중' : p.active ? '측정 상태 확인 필요' : '측정 대기'}</Text>
        <View style={s.row}><Text>측정 시간</Text><Text style={s.value}>{p.duration}</Text></View>
        <View style={s.row}><Text>저장한 GPS</Text><Text style={s.value}>{p.count}개</Text></View>
        <View style={s.row}><Text>최근 GPS 정확도</Text><Text style={s.value}>{p.accuracy == null ? '—' : Math.round(p.accuracy) + ' m'}</Text></View>
        {developer && <><View style={s.row}><Text>최근 GPS 라벨</Text><Text style={s.value}>{p.latestLabel ? MODES.find(m => m.value === currentMode(p.latestLabel!))?.title ?? '—' : '—'}</Text></View>
        {!!p.tripId && <Text selectable style={s.id}>Trip: {p.tripId}</Text>}
        {!!p.eventId && <Text selectable style={s.id}>Event: {p.eventId}{'\n'}측정 시각: {p.eventTime}</Text>}
        <Text style={s.id}>Sequence: {p.sequence??0} / Background Location: {p.backgroundRunning?'등록됨':'꺼짐'}</Text>
        <Text selectable style={s.id}>마지막 GPS 수신: {p.lastReceived??'—'}</Text>
        <Text style={s.id}>전송 대기: {p.pending??0}건 / 마지막 서버 확인: {p.lastSuccess??'—'}</Text>
        {!!p.pending && <Text style={s.id}>가장 오래된 미전송 건의 실패 횟수: {p.retryCount??0}</Text>}
        {!!p.confirmedEvent && <Text selectable style={s.id}>이 Trip의 마지막 API 접수 확인{'\n'}Event: {p.confirmedEvent.event_id}{'\n'}Trip: {p.confirmedEvent.trip_id}{'\n'}Sequence: {p.confirmedEvent.sequence}</Text>}
      </>}
        {!developer && <Text>전송 대기: {p.pending??0}건</Text>}
      </View>
      {developer && !busy && p.resultTrip && <View style={s.card}>
        <Text style={s.status}>측정 결과</Text>
        <Text selectable style={s.id}>Trip: {p.resultTrip.trip_id}</Text>
        <Text>수집: {p.resultTrip.status==='completed' && p.resultTrip.gps_count>0 ? '종료 완료' : '확인 필요'} / {p.resultTrip.gps_count}건 저장</Text>
        <Text>API 접수: {p.sent??0} / {p.resultTrip.gps_count}건</Text>
        <Text>미접수: {Math.max(0,p.resultTrip.gps_count-(p.sent??0))}건 / 오류로 대기: {p.blocked??0}건</Text>
        <Text style={s.note}>{p.resultTrip.gps_count>0 && p.sent===p.resultTrip.gps_count ? '이 Trip은 서버 접수까지 확인됐습니다.' : '미전송 GPS는 보관되며 인터넷 복구 후 전송을 이어갑니다. 오류로 대기 중이면 원인을 해결한 뒤 재시도하세요.'}</Text>
        <Text>Event Hubs / Raw: 원본 대조 대기</Text>
        <Text style={s.note}>측정 결과 파일을 Capture 담당자에게 공유하세요. 저장된 Avro 파일과 대조하면 같은 ID와 모든 원본 값의 보존 여부를 확인할 수 있습니다. 이 화면의 API 접수만으로 2단계 전체 완료로 판정하지 않습니다.</Text>
        <Pressable accessibilityRole="button" disabled={p.sharing} onPress={p.onShareCheck} style={s.export}><Text style={s.modeText}>2단계 확인용 측정 결과 공유</Text></Pressable>
      </View>}
      {!busy && p.resultTrip?.server && <View style={s.card}>
        <Text style={s.status}>Trip 처리 결과</Text>
        <Text>{p.serverTrip?.status==='ready'?'처리 완료':p.serverTrip?.status==='failed'?'처리 실패':p.serverTrip?.status==='processing'?'서버 처리 중':'GPS 전송 및 종료 접수 대기'}</Text>
        {!!p.tripError && <Text style={s.error}>{p.tripError}</Text>}
        {p.serverTrip?.status==='ready' && <TripResult key={p.serverTrip.trip_id} trip={p.serverTrip} pending={p.feedbackPending} onFeedback={p.onFeedback}/>}
        {p.serverTrip?.status==='failed' && <>
          <Text style={s.error}>{p.serverTrip.failed_step}: {p.serverTrip.error_message}</Text>
          <Pressable accessibilityRole="button" onPress={p.onRetryTrip}><Text style={s.modeText}>Trip 처리 재시도</Text></Pressable>
        </>}
      </View>}
      {!!p.error && <Text accessibilityRole="alert" style={s.error}>{p.error}</Text>}
      {!!p.error && <Pressable accessibilityRole="button" onPress={p.onSettings}><Text style={s.modeText}>iPhone 설정 열기</Text></Pressable>}
      {p.active && !p.foregroundOnly && !p.backgroundRunning && !switching && <Pressable accessibilityRole="button" onPress={p.onResume} style={s.export}><Text style={s.modeText}>같은 Trip 재개</Text></Pressable>}
      {!!p.uploadError && <Text style={s.note}>{p.uploadError}</Text>}
      {!!p.pending && <Pressable accessibilityRole="button" onPress={p.onRetry}><Text style={s.modeText}>전송 재시도</Text></Pressable>}
      {p.foregroundOnly && <Text style={s.error}>Expo Go: 이 화면을 켜 둔 상태에서 측정하세요. 화면 잠금·앱 전환 중에는 연속 수집할 수 없습니다.</Text>}
      {developer && <><Pressable accessibilityRole="button" disabled={!p.canShareEvent||p.sharing} onPress={p.onShareEvent} style={[s.export,(!p.canShareEvent||p.sharing)&&s.disabled]}><Text style={s.modeText}>{p.confirmedEvent?'마지막 API 접수 GPS 한 건 공유':'최근 로컬 GPS 한 건 공유'}</Text></Pressable>
      <Text style={s.note}>GPS를 먼저 휴대폰에 저장한 뒤 서버로 전송합니다. 설치형 앱은 잠금·앱 전환 중에도 위치 수집을 요청합니다. 강제 종료 중 수집과 일정한 수신 간격은 보장되지 않습니다.</Text>
      <Pressable accessibilityRole="button" disabled={!p.canExport || busy || p.sharing} onPress={p.onExport}
        style={[s.export, (!p.canExport || busy || p.sharing) && s.disabled]}>
        <Text style={s.modeText}>{p.sharing ? '내보내는 중…' : '저장한 GPS 내보내기'}</Text>
      </Pressable>
      </>}
    </ScrollView>
    <View style={s.footer}><Pressable accessibilityRole="button" disabled={!p.ready || switching || p.sharing || (!busy && developer && !p.mode)}
      onPress={busy ? p.onStop : p.onStart} style={[s.action, busy && s.stop, (!p.ready || switching || p.sharing || (!busy && developer && !p.mode)) && s.disabled]}>
      <Text style={s.actionText}>{p.phase === 'stopping' ? '저장 중…' : busy ? '측정 종료' : '측정 시작'}</Text>
    </Pressable></View>
  </SafeAreaView>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#fff'}, content:{padding:20,gap:16}, title:{fontSize:25,fontWeight:'700',color:'#162922'},
  note:{fontSize:13,color:'#66736e',lineHeight:20}, modes:{flexDirection:'row',flexWrap:'wrap',gap:8},
  mode:{paddingVertical:15,paddingHorizontal:18,borderWidth:1,borderColor:'#cdd6d1',borderRadius:10,minWidth:96,alignItems:'center'},
  selected:{backgroundColor:'#087f5b',borderColor:'#087f5b'}, modeText:{fontSize:16,fontWeight:'600',color:'#174c39'},selectedText:{color:'#fff'},
  label:{fontSize:17,fontWeight:'700'},card:{backgroundColor:'#f3f6f4',padding:18,borderRadius:12,gap:17},
  status:{fontSize:16,fontWeight:'700',color:'#087f5b'},row:{flexDirection:'row',justifyContent:'space-between',gap:10},value:{fontWeight:'700',fontSize:16},
  id:{fontSize:11,color:'#6a746f'},error:{color:'#ad2929',fontSize:14},export:{padding:17,borderWidth:1,borderColor:'#b9cac0',borderRadius:10,alignItems:'center'},
  footer:{padding:20},action:{backgroundColor:'#087f5b',borderRadius:12,padding:19,alignItems:'center'},stop:{backgroundColor:'#ba3535'},
  actionText:{fontSize:18,fontWeight:'700',color:'#fff'},disabled:{opacity:0.4},
});
