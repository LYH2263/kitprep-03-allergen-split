from pydantic import BaseModel


class IngredientPatch(BaseModel):
    is_allergen: bool
