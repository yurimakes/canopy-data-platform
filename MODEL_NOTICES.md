# Model and training-data boundaries

Project code, model parameters and training data have separate provenance and rights. The portfolio's root publication notice does not override dataset conditions or other component licences.

| Component | Portfolio treatment | Boundary |
| --- | --- | --- |
| AI Hub-derived HGB artifact previously reviewed | KEEP under the established audit decision | Raw GPS replay and expected-output derivatives in the 82-path exclusion list are omitted. Retaining trained parameters does not grant access to or redistribute the raw training dataset. |
| SpeedTransformer checkpoint, scaler and label encoder | KEEP under the established audit decision | Preserve project/source attribution. No arbitrary model deserialization was performed during this preparation step. |
| KTDB CatBoost binary and associated restricted reference/result material | Exclude using the established path list | The earlier technical inspection and lack of obvious embedded rows did not establish independent redistribution rights. |
| GeoLife result/report material | Exclude using the established path list | Data loading/evaluation code may remain with source attribution. The raw dataset is not included as a reproducible dependency. |
| Upstream transition detector portion | KEEP with its original MIT notice | [MIT notice](LICENSES/transition-detector-MIT.txt), Copyright (c) 2026 riekim, applies to the identified upstream material rather than the entire repository. |

An earlier KEEP decision is not a new blanket assessment of every binary or every branch. Final mirror verification compares the actual retained paths and objects with these decisions. Examples and evaluation summaries must identify their dataset origin and development scope rather than imply verified production performance.
