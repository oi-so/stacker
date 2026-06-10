from dataclasses import asdict


class SerializableMixin:
    def to_dict(self) -> dict:
        return asdict(self) # type: ignore

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)