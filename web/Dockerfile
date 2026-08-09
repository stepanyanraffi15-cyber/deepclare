FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY deepclare_web ./deepclare_web
RUN pip install --no-cache-dir .

# Public website. Locally this is 8090; on Cloud Run the app binds $PORT (8080)
# instead. EXPOSE is informational only.
EXPOSE 8090

CMD ["python", "-m", "deepclare_web.main"]
