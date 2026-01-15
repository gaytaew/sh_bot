# receipt_product_map.py

"""
Маппинг названий товаров (из листа 'Товары') на ID (Tilda ID),
которые используются в макете Tilda (<select>, product_id и т.д.).
"""

PRODUCT_ID_MAP = {
    # ---- SHOKZ (основная серия) ----
    "Openrun Pro Black": "SH001",
    "Openrun Pro Beige": "SH002",
    "Openrun Pro Blue": "SH003",
    "Openrun Pro Pink": "SH004",
    "OpenDots One Black": "SH021",

    "Openrun Pro Mini Black": "SH005",
    "Openrun Pro Mini Beige": "SH006",

    "Openswim Black": "SH007",
    "Openswim Blue": "SH008",

    "Openfit Black": "SH009",
    "Openfit Beige": "SH010",

    # ---- OpenComm / бизнес-серия ----
    "2025 Opencomm 2 UC USB-C": "SH022",
    "2025 Opencomm 2 UC USB-A": "SH020",

    # ---- Lenovo / Thermopro / Dyson (ранние) ----
    "Lenovo m14t": "LE001",
    "Thermopro Twin": "TP001",
    "Dyson v11": "DY001",

    # ---- OpenRun Pro 2 серия (совпадают с прежними ID) ----
    "Openrun Pro 2 Black": "SH013",
    "Openrun Pro 2 Orange": "SH014",
    "Openrun Pro 2 Silver": "SH015",

    # ---- OpenSwim Pro ----
    "Openswim Pro Gray": "SH017",
    "Openswim Pro Red": "SH018",

    # ---- Dyson (новые модели) ----
    "Dyson Gen5 Outsize": "DY002",
    "Dyson Gen5 Detect": "DY003",
    "Dyson V15 Detect": "DY004",
    "Dyson V15 Absolute Detect": "DY005",
    "Dyson PH04": "DY006",
    "Dyson PH01": "DY007",

    # ---- Mini версии OpenRun Pro 2 ----
    "Openswim Pro Mini Gray": "SH023",
    "Openswim Pro Mini Orange": "SH024",
    "Openswim Pro Mini Silver": "SH025",

    # ---- Dyson ----
    "Dyson v10 Black": "DY008",

    # ---- Wyze / Logitech / Oura / Lenovo / ReMarkable ----
    "Wyze Cam Pro": "WZ001",
    "Logitech G915 TKL": "LG001",

    "Oura Ring Black 10": "OU004",
    "Lenovo M14d": "LE002",
    "Oura Ring Silver 8": "OU005",

    "Remarkable Paper Pro": "RM001",

    # ---- Cefaly ----
    "Cefaly": "CF001",
}
