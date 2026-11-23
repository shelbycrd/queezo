FROM python:3.12-slim-trixie AS sqlite-build
WORKDIR /build
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
# Pin the upstream source used by CPython, independent of Debian's libsqlite3 package.
RUN python -c "import hashlib, io, pathlib, urllib.request, zipfile; archive = urllib.request.urlopen('https://sqlite.org/2026/sqlite-amalgamation-3540100.zip', timeout=45).read(); assert hashlib.sha3_256(archive).hexdigest() == '92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30'; pathlib.Path('sqlite3.c').write_bytes(zipfile.ZipFile(io.BytesIO(archive)).read('sqlite-amalgamation-3540100/sqlite3.c'))" \
    && gcc -O2 -shared -fPIC -Wl,-soname,libsqlite3.so.0 \
       -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_COLUMN_METADATA -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_RTREE \
       sqlite3.c -o libsqlite3.so.0 -lm -ldl -pthread

FROM python:3.12-slim-trixie AS application
COPY --from=sqlite-build /build/libsqlite3.so.0 /opt/queezo/sqlite/libsqlite3.so.0
ENV LD_LIBRARY_PATH=/opt/queezo/sqlite
RUN python -c "import sqlite3; assert sqlite3.sqlite_version == '3.54.1', sqlite3.sqlite_version; print(sqlite3.connect(':memory:').execute('SELECT sqlite_source_id()').fetchone()[0])"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 queezo \
    && mkdir -p /data && chown queezo:queezo /data
COPY backend/ ./
USER queezo
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log", "--ws-max-size", "4096", "--ws-max-queue", "4"]

FROM application AS backup
USER root
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends restic \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 0700 -o queezo -g queezo /backups
USER queezo
ENTRYPOINT ["python", "-m", "app.sqlite_ops"]
CMD ["schedule"]

FROM application AS runtime
