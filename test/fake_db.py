from test.test_globals import PATH_DB_COPY

from prioritysieve.prioritysieve_db import PrioritySieveDB


class FakeDB(PrioritySieveDB):
    # We subclass to use a db with a different file name
    def __init__(self) -> None:
        super().__init__(db_path=PATH_DB_COPY)
