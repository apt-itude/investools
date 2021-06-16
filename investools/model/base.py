import pydantic


def _to_title(string: str) -> str:
    return " ".join(word.capitalize() for word in string.split("_")).strip()


class BaseModel(pydantic.BaseModel):
    class Config:
        alias_generator = _to_title
        allow_population_by_field_name = True
        underscore_attrs_are_private = True
