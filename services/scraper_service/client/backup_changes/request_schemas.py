from typing import Optional, Union, Type
from pydantic import BaseModel, model_validator, ConfigDict


class Pagination(BaseModel):
    start: Optional[int] = None
    page: Optional[int] = None
    batch_size: Optional[int] = None
    pagination_token: Optional[str] = None
    is_query_param: bool = True

    def paginate(self):
        if self.start is not None:
            self.start += self.batch_size
        elif self.page is not None:
            self.page += 1
    
    def get_params(self):
        kwargs = {}
        if self.start is not None:
            kwargs["start"] = self.start
        elif self.page is not None:
            kwargs["page"] = self.page
        if self.pagination_token is not None:
            kwargs["pagination_token"] = self.pagination_token
        if self.is_query_param:
            return kwargs
        return {}

    @model_validator(mode="after")
    def validate_pagination(self):
        if self.start and self.page:
            raise ValueError("start and page cannot both be provided")
        if not self.start and not self.page:
            raise ValueError("start or page must be provided")


class ParseResponseConfig(BaseModel):
    # NOTE: None means the entire payload is the data!
    data_field_name: Optional[str] = None
    list_items_field_name: Optional[str] = None
    is_list: bool = False


class ResponseBaseModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    @classmethod
    def parse_response(cls, data: dict):
        return cls.model_construct(**data)


class APIRequest(BaseModel):
    endpoint: str
    method: str
    pagination: Optional[Pagination] = None
    batch_limit: Optional[int] = None
    
    # NOTE: These are validated query params and payload
    query_params: Optional[BaseModel] = None
    payload: Optional[BaseModel] = None

    parse_response_config: Optional[ParseResponseConfig] = None

    # NOTE: This is used to Annotate, validation never fails!
    response_model: Optional[Type[ResponseBaseModel]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_query_params(self):
        kwargs = {}
        if self.pagination and self.pagination.is_query_param:
            kwargs.update(self.pagination.get_params())
        if self.query_params:
            kwargs.update(self.query_params)
        return kwargs
    
    def get_body_payload(self):
        kwargs = {}
        if self.pagination and not self.pagination.is_query_param:
            kwargs.update(self.pagination.get_params())
        if self.payload:
            kwargs.update(self.payload)
        return kwargs

    def parse_response(self, response_data: Union[dict, str]):
        if self.parse_response_config and self.parse_response_config.data_field_name:
            return response_data[self.parse_response_config.data_field_name]
        return response_data


if __name__ == "__main__":
    class ProfileResponse(ResponseBaseModel):
        id: str
        name: str
        age: Optional[int] = None

    m = ResponseBaseModel.parse_response({"id": 1, "name": "John", "age": 20.2, "extra": "extra", "xxx": None})
    mm = ProfileResponse.parse_response({"id": 1, "name": "John", "age": 20.2, "extra": "extra", "xxx": None})

    print(m.model_dump_json(indent=4), "\n\n")
    print(m.model_dump(), "\n\n")
    print(mm.model_dump_json(indent=4), "\n\n")
    print(mm.model_dump(), "\n\n")
