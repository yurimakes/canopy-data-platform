# Data sources and example scope

This portfolio edition distinguishes public transport reference data, project evaluation examples, and restricted material omitted from the public history. The source dates below describe the project inputs, not today's latest timetable or traffic information. No provider endorses CANOPY.

## Public transport reference

The project normalizes source columns into CSV reference tables. Public facility coordinates, station/stop identifiers and published service times describe transport infrastructure. These files are not individual travel histories.

| Project CSV | Provider and input recorded in the CSV | Rows per reviewed content version | Source and use notice |
| --- | --- | ---: | --- |
| korail_stations.csv | 한국철도공사, 역 위치 정보, 2024-04-01 | 202 | [Public Data Portal](https://www.data.go.kr/data/15127532/fileData.do): use scope unrestricted, checked 2026-10-07 |
| subway_stations.csv | 서울교통공사, 1–8호선 역사 좌표(위경도) 정보, 2025-08-14 | 276 | [Public Data Portal](https://www.data.go.kr/data/15099316/fileData.do); [Seoul source](https://data.seoul.go.kr/dataList/OA-22534/F/1/datasetView.do): KOGL Type 1 attribution |
| seoul_bus_stops.csv | 서울특별시, 서울시버스노선별정류소정보, 2026-08-04 | 12,898 | [Seoul source](https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do): the 20260804 XLSX remains listed; KOGL Type 1 attribution |
| seoul_bus_route_stops.csv | Same Seoul bus source, normalized route-stop relationships | 41,676 | Same source and attribution; the normalized output differs from the original workbook |
| subway_timetable.csv | 서울교통공사, 서울 도시철도 열차운행시각표, project input 2026-06-16 | 424,264 | [Public Data Portal](https://www.data.go.kr/data/15098251/fileData.do); [Seoul source](https://data.seoul.go.kr/dataList/OA-22522/F/1/datasetView.do) |

The timetable portal currently names the 2026-09-01 edition and declares unrestricted use. The Seoul page declares KOGL Type 1 and lists a 2025-09-30 file. These pages are source references; they do not prove a byte-for-byte match or the archived terms of the project's June input. The project preserves the June source label and attribution rather than changing it to September. This version-specific evidence limit remains recorded in the release audit.

Transport CSVs occur in retained Databricks runtime asset folders and in historical aliases. `tools/local/setup_transit.py` accepts `--source` for a folder containing all five CSVs and writes local hashes in `.local-data/transit/provenance.json`. It uses the retained local files; a personal upstream repository checkout is no longer required.

## Greenhouse gas factors

The retained `emission_factors_2026.csv` identifies UK Government GHG Conversion Factors for Company Reporting, source year 2026, and original source-row identifiers. The project normalizes units from kg CO2e to gCO2e and retains source values and units for traceability.

Source: Department for Energy Security and Net Zero, [Greenhouse gas reporting: conversion factors 2026](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026). The publication offers the full set issued in June and a flat file corrected in July. The project CSV alone does not establish which workbook bytes were downloaded. Its values must not be described as a verified copy of the July correction.

Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Crown copyright and applicable third-party rights remain with their holders; the OGL excludes personal information, logos and rights that the provider cannot license.

These factors support UK activity reporting. CANOPY uses selected values as a development proxy, not as official Korean emissions factors or verified emissions accounting. Walking/cycling zero values reflect the project's operational boundary and policy; they do not assert zero lifecycle environmental impact.

## Evaluation and collected demonstration input

The four retained dataset_v1 baseline/improvement JSONL outputs belong to the project README's synthetic evaluation dataset. They include trip-level/window-level predictions and ground-truth labels. The source audit read all 85,996,435 bytes and processed 153,410 JSON lines; the configured email/phone/personal-path/GPS/ID patterns returned no hits. This describes the checks performed, not a general guarantee about all identifiers or training data rights.

`canopy_iphone_mock_yeongdeungpo_to_microsoft.csv` is a retained 433-row demonstration route. Despite its historical filename, it may contain directly collected iPhone location samples. The portfolio maintainer confirmed retaining it for public presentation on 2026-10-07. It is not described as verified synthetic data. This confirmation is specific to that input and does not include other collected location records.

## Material excluded from public history

The prepared exclusion list has 82 paths covering AI Hub raw-derived replay fixtures, GeoLife result/report files, KTDB model/reference/result files, and one retained TMAP response fixture. Their processing code and source attribution are preserved where safe. An exclusion does not assert that the original private project violated a licence.

The retained KTDB `raw_manifest.json` records filenames, sizes, timestamps and file hashes only; it does not distribute the four underlying source files or their personal-data rows. It is provenance metadata, not proof that the underlying dataset or model may be redistributed.

See [MODEL_NOTICES.md](MODEL_NOTICES.md) for retained model boundaries and [NOTICE.md](NOTICE.md) for component rights.
