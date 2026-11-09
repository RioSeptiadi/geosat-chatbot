from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MYSQL_HOST: str
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB: str
    MYSQL_PORT: int = 3306
    WA_TOKEN: str
    WA_PHONE_NUMBER_ID: str
    WA_VERIFY_TOKEN: str
    WA_APP_SECRET: str
    QWEN_API_KEY: str
    QWEN_BASE_URL: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    class Config:
        env_file = ".env"

settings = Settings()