"""
Value Objects: ProductAttributes
=================================
Type-safe wrappers cho JSONB attributes của từng loại sản phẩm.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BookAttributes:
    author: str
    isbn: Optional[str] = None

    def to_dict(self) -> dict:
        return {"author": self.author, "isbn": self.isbn}

    @classmethod
    def from_dict(cls, d: dict) -> "BookAttributes":
        return cls(author=d.get("author", ""), isbn=d.get("isbn"))


@dataclass(frozen=True)
class ClothAttributes:
    brand: str
    size: str
    color: str

    def to_dict(self) -> dict:
        return {"brand": self.brand, "size": self.size, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> "ClothAttributes":
        return cls(
            brand=d.get("brand", ""),
            size=d.get("size", ""),
            color=d.get("color", ""),
        )


def make_attributes(product_type: str, data: dict):
    """Factory: trả về đúng value object theo product_type."""
    if product_type == "book":
        return BookAttributes.from_dict(data)
    elif product_type == "cloth":
        return ClothAttributes.from_dict(data)
    raise ValueError(f"Unknown product_type: {product_type}")
