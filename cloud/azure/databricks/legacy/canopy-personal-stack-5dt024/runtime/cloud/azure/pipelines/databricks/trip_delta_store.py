"""Trip 저장 대상 연결. 운영은 Managed Table, 기존 경로는 이전·복구용 지원."""
import re


def table_name(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError("expected catalog.schema.table")
    return value


def is_path(value):
    return value.startswith(("abfss://", "dbfs:/", "file:/", "/"))


def quoted(value):
    return ".".join("`" + part + "`" for part in table_name(value).split("."))


def exists(spark, target):
    if is_path(target):
        from delta.tables import DeltaTable
        return DeltaTable.isDeltaTable(spark, target)
    return spark.catalog.tableExists(table_name(target))


def read(spark, target):
    return spark.read.format("delta").load(target) if is_path(target) else spark.read.table(table_name(target))


def assert_managed_delta(spark, target):
    rows = spark.sql("DESCRIBE TABLE EXTENDED " + quoted(target)).collect()
    metadata = {r.col_name.strip(): r.data_type.strip() for r in rows}
    if metadata.get("Type", "").upper() != "MANAGED" or metadata.get("Provider", "").lower() != "delta":
        raise ValueError("target must be a Unity Catalog managed Delta table: " + target)


def initialize(spark, target, frame):
    # 빈 테이블 생성 후 호출자가 MERGE. 동시 최초 저장에서 행 누락 방지.
    writer = frame.limit(0).write.format("delta").mode("ignore")
    if is_path(target):
        if not exists(spark, target):
            writer.save(target)
    else:
        table_name(target)
        if not exists(spark, target):
            writer.saveAsTable(target)
        assert_managed_delta(spark, target)


def delta(spark, target):
    from delta.tables import DeltaTable
    if is_path(target):
        return DeltaTable.forPath(spark, target)
    assert_managed_delta(spark, target)
    return DeltaTable.forName(spark, table_name(target))


def test_target(target):
    if is_path(target):
        return "/pipeline_test/" in target
    table_name(target)
    return target.split(".")[1] in ("sandbox", "pipeline_test")


def add_target(parser, name, required=True):
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--" + name + "-table", type=table_name, help="Managed Delta: catalog.schema.table")
    group.add_argument("--" + name + "-path", help="기존 Delta 경로: 이전 및 복구용")


def target_arg(args, name):
    return getattr(args, name + "_table") or getattr(args, name + "_path")
