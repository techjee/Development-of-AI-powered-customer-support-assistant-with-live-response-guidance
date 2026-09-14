from database import Base, engine, ensure_auth_schema
import models


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    ensure_auth_schema()
    print("Created schema tables:", ", ".join(sorted(Base.metadata.tables)))
