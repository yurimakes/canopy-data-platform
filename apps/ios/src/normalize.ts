import type { LocationObject } from 'expo-location';
import { SCHEMA, currentMode, type TransportMode, type GpsEvent, type Trip } from './types';
const finite = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
export function normalize(raw: LocationObject, trip: Trip, sequence: number, id: string,
  received: string, previous?: GpsEvent | null, mode: TransportMode | null = null): GpsEvent {
  const c = raw?.coords;
  if (!c || !finite(c.latitude) || !finite(c.longitude) || Math.abs(c.latitude) > 90 || Math.abs(c.longitude) > 180)
    throw new Error('invalid_coordinates');
  if (!finite(raw.timestamp) || !Number.isFinite(new Date(raw.timestamp).getTime())) throw new Error('invalid_timestamp');
  const flags: string[] = [];
  const optional = (v: unknown, name: string, min = -Infinity, max = Infinity) => {
    if (finite(v) && v >= min && v < max) return v;
    flags.push(`${name}_unavailable`); return null;
  };
  const event_time = new Date(raw.timestamp).toISOString();
  if (previous && event_time === previous.event_time) flags.push('duplicate_timestamp');
  if (previous && event_time < previous.event_time) flags.push('timestamp_reversal');
  const accuracy = optional(c.accuracy, 'accuracy', 0);
  // Diagnostic label only. Never a rejection/filter or ML input rule.
  if (accuracy !== null && accuracy > 100) flags.push('accuracy_above_100m');
  const label=mode===null?null:currentMode(mode);
  const annotation=trip.schema_version===SCHEMA
    ? {collection_mode:label===null?'user' as const:'developer' as const,label}
    : label===null?{}:{label:label==='walk'?'walking' as const:label==='bike'?'cycling' as const:label==='rail'?'subway' as const:label};
  return { ...annotation, schema_version: trip.schema_version, event_id: id, user_id: trip.user_id, device_id: trip.device_id,
    trip_id: trip.trip_id, sequence, event_time, received_at: received, lat: c.latitude, lon: c.longitude,
    accuracy, speed: optional(c.speed, 'speed', 0), altitude_m: optional(c.altitude, 'altitude'),
    vertical_accuracy_m: optional(c.altitudeAccuracy, 'vertical_accuracy', 0),
    course_deg: optional(c.heading, 'course', 0, 360), source: 'expo-location.foreground',
    quality_flags: flags, raw_location: raw };
}
// JSON cannot represent NaN/Infinity/undefined. Preserve exceptional raw values explicitly.
export const encode = (value: unknown) => JSON.stringify(value, (_key, v) =>
  typeof v === 'number' && !Number.isFinite(v) ? { non_json_number: String(v) } :
    v === undefined ? { non_json_value: 'undefined' } : v);
