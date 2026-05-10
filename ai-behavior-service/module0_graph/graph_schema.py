"""
Graph Schema — Định nghĩa các loại Node và Edge trong Knowledge Graph.
"""

# =============================================
# NODE TYPES
# =============================================
class NodeType:
    BOOK      = "Book"
    CLOTHES   = "Clothes"
    PRODUCT   = "Product"   # generic — electronics, furniture, etc.
    AUTHOR    = "Author"
    BRAND     = "Brand"
    CATEGORY  = "Category"
    SCENARIO  = "Scenario"
    USER      = "User"      # e-commerce user node


# =============================================
# EDGE TYPES
# =============================================
class EdgeType:
    WRITTEN_BY      = "WRITTEN_BY"      # Book -> Author
    IN_CATEGORY     = "IN_CATEGORY"     # Book/Clothes -> Category
    MADE_BY         = "MADE_BY"         # Clothes -> Brand
    SUITS           = "SUITS"           # Category -> Scenario
    ALIAS           = "ALIAS"           # Brand -> Brand (LV <-> Louis Vuitton)
    SAME_AUTHOR     = "SAME_AUTHOR"     # Book -> Book (cùng tác giả)
    SAME_BRAND      = "SAME_BRAND"      # Clothes -> Clothes (cùng hãng)
    SIMILAR         = "SIMILAR"         # Product -> Product (cùng category)
    # User interaction edges (weight = interaction strength)
    VIEWED          = "VIEWED"          # User -> Product  (weight=1)
    ADDED_TO_CART   = "ADDED_TO_CART"   # User -> Product  (weight=3)
    PURCHASED       = "PURCHASED"       # User -> Product  (weight=5)


# =============================================
# BRAND ALIASES (đồng bộ với kb_builder.py)
# =============================================
BRAND_ALIASES = {
    "Louis Vuitton": ["LV"],
    "Yves Saint Laurent": ["YSL", "Saint Laurent"],
    "Christian Dior": ["Dior", "CD"],
    "Gucci": ["GG"],
    "Chanel": ["CC"],
    "Hermes": ["Hermès", "Hermès"],
    "Balenciaga": ["BLCG"],
    "Versace": [],
    "Prada": [],
    "Burberry": [],
}

# Reverse lookup: alias (lowercase) -> canonical
ALIAS_TO_BRAND: dict[str, str] = {}
for _canon, _aliases in BRAND_ALIASES.items():
    ALIAS_TO_BRAND[_canon.lower()] = _canon
    for _a in _aliases:
        ALIAS_TO_BRAND[_a.lower()] = _canon


def resolve_brand(token: str) -> str | None:
    """Trả về canonical brand name nếu token là brand/alias, ngược lại None."""
    return ALIAS_TO_BRAND.get(token.strip(".,!?\"'()").lower())
