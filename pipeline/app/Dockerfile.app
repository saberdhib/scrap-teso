FROM python:3.12-slim

RUN pip install --no-cache-dir streamlit>=1.38 psycopg2-binary>=2.9 pandas>=2.2

WORKDIR /app
COPY app/review_app.py /app/app/review_app.py
COPY src /app/src

EXPOSE 8501
CMD ["streamlit", "run", "app/review_app.py", "--server.address=0.0.0.0"]
