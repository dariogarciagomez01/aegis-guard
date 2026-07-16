from sqlmodel import Session, select
from src.database.connection import engine, init_db
from src.database.models import User, ApiKey

def seed_database():
    print("Inicializando base de datos y tablas...")
    init_db()

    with Session(engine) as session:
        # Check if our test user already exists to avoid duplication
        statement = select(User).where(User.username == "dario_dev")
        existing_user = session.exec(statement).first()

        if existing_user:
            print("El usuario de pruebas 'dario_dev' ya existe. Saltando inyección.")
            return

        print("Creando usuario de pruebas: dario_dev...")
        test_user = User(username="dario_dev", is_active=True)
        session.add(test_user)
        session.commit()  # Commit to generate the user.id
        session.refresh(test_user)

        print("Generando Aegis Guard API Key para el usuario...")
        # Hardcoding a recognizable test key for local development
        test_key = ApiKey(
            key="ak_live_dario123456789",
            user_id=test_user.id,
            is_active=True,
            rate_limit_rpm=5  # We set a low limit of 5 requests per minute for testing later
        )
        session.add(test_key)
        session.commit()

        print("\n ¡Base de datos inyectada con éxito!")
        print(f"-> Tu API Key de Aegis Guard es: {test_key.key}")
        print(f"-> Límite asignado: {test_key.rate_limit_rpm} peticiones por minuto (RPM).")

if __name__ == "__main__":
    seed_database()