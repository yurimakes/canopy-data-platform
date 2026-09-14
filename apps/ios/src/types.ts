import type { LocationObject } from 'expo-location';
export const SCHEMA = 'canopy.gps.collector.v0.2' as const;
export const LEGACY_SCHEMA = 'canopy.gps.collector.v0.1' as const;
export const MODES = [
  { value: 'walk', title: '걷기' }, { value: 'bike', title: '자전거' },
  { value: 'car', title: '자동차' }, { value: 'bus', title: '버스' },
  { value: 'rail', title: '철도·지하철' },
] as const;
export type TransportMode = typeof MODES[number]['value'];
export type LegacyMode = 'walking' | 'cycling' | 'subway';
export function currentMode(mode: TransportMode | LegacyMode): TransportMode {
  return mode==='walking'?'walk':mode==='cycling'?'bike':mode==='subway'?'rail':mode;
}
export type Identity = { user_id: string; device_id: string };
export type GpsEvent = Identity & {
  schema_version: typeof SCHEMA | typeof LEGACY_SCHEMA; event_id: string; trip_id: string; sequence: number;
  event_time: string; received_at: string; lat: number; lon: number;
  accuracy: number | null; speed: number | null; altitude_m: number | null;
  vertical_accuracy_m: number | null; course_deg: number | null;
  source: 'expo-location.foreground' | 'expo-location.background'; quality_flags: string[]; raw_location: LocationObject;
  // Older recordings have no manual label. Never infer labels for them.
  label?: TransportMode | LegacyMode | null;
  collection_mode?: 'user' | 'developer';
};
// Strict producer contract; GpsEvent above also reads unchanged v0.1 records.
export type CurrentGpsEvent = Omit<GpsEvent,'schema_version'|'label'|'collection_mode'> & {
  schema_version: typeof SCHEMA;
} & ({collection_mode:'user';label:null} | {collection_mode:'developer';label:TransportMode});
export type Trip = Identity & {
  trip_id: string; schema_version: typeof SCHEMA | typeof LEGACY_SCHEMA; started_at: string; ended_at: string | null;
  status: 'recording' | 'completed' | 'interrupted'; interruption_reason: string | null;
  recovered_at: string | null; foreground_only: boolean;
  collection_settings: Record<string, unknown>; environment: Record<string, unknown>;
};
export type Summary = Trip & { gps_count: number; first_event_time: string | null;
  last_event_time: string | null; last_saved_at: string | null; latest: GpsEvent | null };
export type Diagnostic = { recorded_at: string; kind: string; detail: unknown };
