"""Temporal confirmation over unchanged HGB probabilities, shared by final/live."""
from dataclasses import dataclass, field
from datetime import datetime
import math
import statistics

VERSION = 'mode-confirmation-v1'
CONFIRMATIONS = 3
MARGIN = 0.15
STRONG_CONFIRMATIONS = 2


def at(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def stationary(points):
    # Require actual phone speed evidence. Missing speed is not evidence of rest.
    speeds = [p.get('raw_speed') for p in points]
    valid = [v for v in speeds if isinstance(v, (int, float)) and not isinstance(v, bool)
             and math.isfinite(v) and v >= 0]
    return bool(points) and len(valid) >= .8 * len(points) and statistics.median(valid) <= .5


@dataclass
class TransitionState:
    active: str | None = None
    candidate: str | None = None
    candidate_start: str | None = None
    margins: list = field(default_factory=list)
    last_end: str | None = None

    def clear_candidate(self):
        self.candidate = None
        self.candidate_start = None
        self.margins.clear()

    def step(self, row, *, live=False):
        end = row['end_time']
        if live and self.last_end and (at(end)-at(self.last_end)).total_seconds() < 10:
            return self.active or row['mode'], None, 'already_observed'
        if self.last_end and (at(row['start_time'])-at(self.last_end)).total_seconds() > .01:
            self.clear_candidate()
        self.last_end = end
        proposed = row['mode']
        if self.active is None:
            self.active = proposed
            return self.active, None, 'initial_prediction'
        if row.get('stationary'):
            self.clear_candidate()
            return self.active, None, 'stationary_hold'
        if proposed == self.active:
            self.clear_candidate()
            return self.active, None, 'current_mode_retained'
        if self.candidate != proposed:
            self.clear_candidate()
            self.candidate = proposed
            self.candidate_start = row['start_time']
        p = row.get('probabilities', {})
        self.margins.append(p.get(proposed, 0)-p.get(self.active, 0) >= MARGIN)
        self.margins = self.margins[-CONFIRMATIONS:]
        if len(self.margins) == CONFIRMATIONS and sum(self.margins) >= STRONG_CONFIRMATIONS:
            start = self.candidate_start
            self.active = proposed
            self.clear_candidate()
            return self.active, start, 'transition_confirmed'
        return self.active, None, 'candidate_pending'


def smooth_modes(rows, state=None):
    live = state is not None
    state = state or TransitionState()
    output = []
    previous_run = None
    for original in rows:
        row = dict(original)
        if previous_run is not None and previous_run != row['run']:
            state.clear_candidate()
        previous_run = row['run']
        mode, boundary, reason = state.step(row, live=live)
        row['mode'] = mode
        row['confidence'] = row.get('probabilities', {}).get(mode, row['confidence'])
        row['smoothing'] = {'version': VERSION, 'original_mode': original['mode'],
                            'final_mode': mode, 'reason': reason}
        output.append(row)
        if boundary is not None:
            for prior in output:
                if prior['run'] == row['run'] and at(prior['start_time']) >= at(boundary):
                    prior['mode'] = mode
                    prior['confidence'] = prior.get('probabilities', {}).get(mode, prior['confidence'])
                    prior['smoothing'].update(final_mode=mode, reason='confirmed_candidate_interval')
    return output
