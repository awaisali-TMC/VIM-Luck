# Running `test_role_labels.py`

Covers role display names: that a rename reaches every screen, that it changes
one column of one row and nothing else, and that access control keeps working
off the role **key**.

## SQLite (quick, the default)

```powershell
py -3 backend/test_role_labels.py
```

Uses a throwaway SQLite file in the system temp directory. Delete it to start
clean; the suite is also re-runnable as is.

## Postgres 16 — the run that matters

The cloud runs Postgres, which enforces `VARCHAR` lengths and unique
constraints that SQLite silently ignores. An over-long role name is a 500 on
Postgres and a silent success on SQLite, so validation changes must be proven
here.

```powershell
docker run -d --name rl-pg -e POSTGRES_PASSWORD=rolelabels -e POSTGRES_DB=roletest `
  -p 127.0.0.1:55432:5432 postgres:16

$env:ROLE_LABELS_DB = "postgresql+asyncpg://postgres:rolelabels@127.0.0.1:55432/roletest"
py -3 backend/test_role_labels.py
```

Reset between runs (the suite never drops anything itself):

```powershell
docker exec rl-pg psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS roletest WITH (FORCE);" -c "CREATE DATABASE roletest;"
```

Independent witness of what the run did, straight from the database:

```powershell
docker exec rl-pg psql -U postgres -d roletest -c "SELECT key, label, is_system FROM roles ORDER BY id;"
```

Tear down: `docker rm -f rl-pg`.

## It will not touch a real database

`ROLE_LABELS_DB` is checked before the app is imported, and the run aborts with
exit code 2 unless it is a scratch SQLite file, or Postgres on loopback, not on
port 5432, with the database named `roletest`. Addresses containing `cloudsql`,
`.run.app` or a customer name are refused outright. As a last check the suite
aborts if `invoices` or `internal_users` already contain rows. It contains no
`DROP` or `TRUNCATE`; resets are done by hand with the command above.

## Proving the suite is honest

Run it against the code from before the rename — the propagation tests must
fail while the safety tests still pass:

```powershell
git worktree add /tmp/vim-old 73e968d
cp backend/test_role_labels.py /tmp/vim-old/backend/
cd /tmp/vim-old/backend; py -3 test_role_labels.py     # expect failures in A and B
git worktree remove /tmp/vim-old
```

The suite also carries its own negative control: it neuters `role_labels()`
mid-run and checks the name degrades to the humanised key, which proves the
names are read from the database rather than matching by luck.
