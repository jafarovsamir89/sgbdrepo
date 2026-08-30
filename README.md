# BMW F/G SGBD Diagnostic Database

Цель проекта — построить нормализованную базу диагностических функций BMW F/G-series из SGBD/PRG/GRP и проверяемых диагностических источников.

## Scope

В базу включаются только:

- **Live Data**: UDS `0x22 ReadDataByIdentifier`, `0x2C DynamicallyDefineDataIdentifier`.
- **Basic Active Tests**: UDS `0x2F InputOutputControlByIdentifier`, безопасные диагностические `0x31 RoutineControl`.

Не включаются в основной runtime-каталог:

- flashing/programming (`0x34/0x36/...`);
- SecurityAccess algorithms;
- immobilizer/key/ISN operations;
- VIN/odometer manipulation;
- airbag deployment or destructive routines;
- EEPROM editing;
- coding/programming routines.

## Главный принцип

Функции привязываются **не просто к имени ECU (DME/DSC/SMFA)**, а к конкретному диагностическому варианту **SGBD**.

Пример:

```text
DME
├── mevd1724
├── mevd1726
├── dme_bx8
└── ...
```

У каждого варианта свои DID/RID, scaling, enum-таблицы и поддерживаемые функции.

## Человекочитаемые названия

Оригинальное BMW-имя всегда сохраняется в `source_label`, но UI использует нормализованные поля:

```json
{
  "canonical_id": "ENGINE.RPM",
  "name_ru": "Обороты двигателя",
  "name_en": "Engine speed",
  "source_label": "STAT_0X592A_WERT"
}
```

Технические имена вроде `STAT_0X592A_WERT`, `INMOT`, `STEUERN_IO` не должны отображаться обычному пользователю.

## Структура

```text
data/
  ecu_catalog.json
  functions/
    dme/
    dde/
    transmission/
    chassis/
    body/
    climate/
    seats/
    infotainment/

schema/
  diagnostic-function.schema.json

config/
  naming_rules.json
  source_policy.json

scripts/
  build_db.py
  normalize_names.py
```

## Модель функции

Каждая запись содержит как минимум:

- `ecu_family`
- `sgbd`
- `function_type`
- `canonical_id`
- `name_ru`
- `name_en`
- `source_label`
- `service`
- `identifier`
- тип/длину данных
- scaling (`multiply`, `divide`, `offset`)
- `unit`
- enum/result table при наличии
- requirements/conditions
- source/confidence

## Confidence

Источники маркируются:

1. `OEM_PRG`
2. `OEM_ISTA`
3. `PRG_BYTECODE`
4. `VERIFIED_CAPTURE`
5. `VERIFIED_VEHICLE`
6. `OPEN_SOURCE`
7. `THIRD_PARTY`
8. `FORUM`
9. `UNVERIFIED`

Runtime по умолчанию должен использовать только высокодоверенные записи.

## Источники

Первичный публичный источник для bootstrap:

- `emdzej/ediabasx-docs-sgbd` — автоматически сгенерированная документация SGBD/PRG/GRP (2466 файлов на момент bootstrap).

Дополнительная верификация:

- BMW ISTA/EDIABAS/Tool32 данные;
- реальные ENET/DoIP captures;
- open-source BMW diagnostic implementations;
- third-party scanner behaviour только как secondary evidence.

## Статус

Проект в стадии построения базы. Первый приоритет:

1. DME/DDE
2. EGS
3. DSC
4. FEM/BDC
5. IHKA
6. EPS/EMF
7. ACSM
8. SMFA/SMBF/seat modules
9. HKFM
10. NBT/NBTEVO/MGU
