"""
Константы и конфигурационные данные для бота Shokz.
"""
from issues import ISSUE_TEMPLATES, CEFALY_ISSUE_TEMPLATES
from receipt_product_map import PRODUCT_ID_MAP

# --- СЛОВАРИ СИНОНИМОВ ДЛЯ АДРЕСА ---
STREET_SYNONYMS = {
    "RD": ["Road", "Roud", "Rd."],
    "ST": ["Street", "Strt", "St."],
    "CT": ["Court", "Ct."],
    "AVE": ["Avenue", "Ave."],
    "LN": ["Lane", "Lnae"],
    "PL": ["Place", "Plce"],
    "GR": ["Grove", "Gr."],
    "DR": ["Drive", "Dr."],
    "TER": ["Terrace", "Ter."],
    "APT": ["Apartments", "Apartment", "Aprt", "Aprts", "Apt."],
}

DIRECTION_SYNONYMS = {
    "N": ["North", "Nth"],
    "S": ["South", "Sth"],
    "E": ["East", "Est"],
    "W": ["West", "Wst"],
}

# --- ИМПОРТ ШАБЛОНОВ ПРИЧИН ---
# ISSUE_TEMPLATES импортируется из issues.py

# --- МАППИНГ ТОВАРОВ ---
# PRODUCT_ID_MAP импортируется из receipt_product_map.py

