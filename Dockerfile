FROM python:3.12-slim
WORKDIR /app
COPY pdp.py /app/pdp.py
EXPOSE 8080
CMD ["python", "pdp.py"]
