FROM python:3.12-slim

RUN pip install --no-cache-dir "streamlit>=1.38" "psycopg2-binary>=2.9" \
        "pandas>=2.2" "plotly>=5.24"

WORKDIR /app
COPY app /app/app
COPY src /app/src

EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0"]
