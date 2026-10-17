from pydantic import BaseModel, ConfigDict


class Dto(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
