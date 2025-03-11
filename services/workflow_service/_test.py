from global_config.settings import settings

print(settings.DATABASE_URL)

from db.session import get_session

# session = get_session()


from _test_import import x

print(x)

