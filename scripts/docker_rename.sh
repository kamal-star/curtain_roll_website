#!/usr/bin/env bash
# Move the live Docker site from the app `curtain_roll` to `kayan_curtain`.
#
# Run on the Docker HOST (not inside a container), once:
#
#     bash scripts/docker_rename.sh
#
# Defaults match the live server; override any of them from the environment,
# e.g.  SITE=othersite bash scripts/docker_rename.sh
#
# What it does, in the only order that works (see "Renaming from curtain_roll"
# in README.md - the old app must stay importable until the database is moved):
#   1. backs up the site
#   2. puts kayan_curtain NEXT TO curtain_roll in every container that has it
#   3. runs kayan_curtain.rename_app.run against the database
#   4. takes curtain_roll out of the bench (its folder is kept for rollback)
#   5. links the assets, migrates, clears caches, restarts the containers
set -euo pipefail

BACKEND="${BACKEND:-dwherp-erpnext_backend-1}"
SITE="${SITE:-frontend}"
BRANCH="${BRANCH:-claude/great-davinci-qyhovm}"
BENCH="${BENCH:-/home/frappe/frappe-bench}"
# Name prefix of this stack's containers; workers and the scheduler run our
# hooks too, so each one that has curtain_roll gets the new app as well.
PREFIX="${PREFIX:-${BACKEND%%_*}_}"
# Only needed when apps/curtain_roll in the container is not a git checkout:
# a checkout of this repo on the host, copied in with `docker cp`.
SRC="${SRC:-}"

say() { printf '\n==> %s\n' "$*"; }
in_c() { local c="$1"; shift; docker exec "$c" bash -c "cd '$BENCH' && $*"; }

docker inspect "$BACKEND" >/dev/null 2>&1 || {
	echo "Container $BACKEND not found (docker ps to check its name)"; exit 1; }

# every running container of this stack that has the old app's code
CODE_CONTAINERS=("$BACKEND")
for c in $(docker ps --format '{{.Names}}' | grep "^${PREFIX}" || true); do
	[[ "$c" == "$BACKEND" ]] && continue
	if docker exec "$c" test -d "$BENCH/apps/curtain_roll" 2>/dev/null \
		|| docker exec "$c" test -d "$BENCH/apps/kayan_curtain" 2>/dev/null; then
		CODE_CONTAINERS+=("$c")
	fi
done
echo "Site:       $SITE"
echo "Containers: ${CODE_CONTAINERS[*]}"

say "1/5 Backup of $SITE"
in_c "$BACKEND" "bench --site '$SITE' backup --with-files"

say "2/5 kayan_curtain alongside curtain_roll"
for c in "${CODE_CONTAINERS[@]}"; do
	echo "-- $c"
	if [[ -n "$SRC" ]]; then
		in_c "$c" "rm -rf apps/kayan_curtain"
		docker cp "$SRC/." "$c:$BENCH/apps/kayan_curtain"
	elif docker exec "$c" test -d "$BENCH/apps/kayan_curtain/.git"; then
		in_c "$c" "cd apps/kayan_curtain && git fetch -q origin '$BRANCH' && git checkout -q -B '$BRANCH' FETCH_HEAD"
	elif docker exec "$c" test -d "$BENCH/apps/curtain_roll/.git"; then
		# a local clone shares the old checkout's objects, so only the new
		# commits come over the network. bench get-app names the remote
		# `upstream`, not `origin` - take whichever the old checkout has.
		in_c "$c" "cd apps \
			&& git clone -q --no-checkout curtain_roll kayan_curtain \
			&& cd kayan_curtain \
			&& git remote set-url origin \"\$(git -C ../curtain_roll remote get-url \$(git -C ../curtain_roll remote | head -n1))\" \
			&& git fetch -q origin '$BRANCH' \
			&& git checkout -q -B '$BRANCH' FETCH_HEAD"
	else
		echo "apps/curtain_roll in $c is not a git checkout."
		echo "Re-run with SRC=/path/to/a/checkout/of/branch/$BRANCH"
		exit 1
	fi
	in_c "$c" "test -f apps/kayan_curtain/kayan_curtain/rename_app.py" || {
		echo "apps/kayan_curtain in $c is not the renamed app (branch $BRANCH?)"; exit 1; }
	in_c "$c" "./env/bin/pip install -q --no-deps -e apps/kayan_curtain"
done
# sites/ is a shared volume - one edit covers every container
in_c "$BACKEND" "grep -qx kayan_curtain sites/apps.txt || { [ -z \"\$(tail -c1 sites/apps.txt)\" ] || echo >> sites/apps.txt; echo kayan_curtain >> sites/apps.txt; }"

say "3/5 Database: curtain_roll -> kayan_curtain"
in_c "$BACKEND" "bench --site '$SITE' execute kayan_curtain.rename_app.run"

say "4/5 curtain_roll out of the bench"
in_c "$BACKEND" "sed -i '/^curtain_roll\$/d' sites/apps.txt"
for c in "${CODE_CONTAINERS[@]}"; do
	echo "-- $c"
	in_c "$c" "./env/bin/pip uninstall -y -q curtain_roll || true"
	# kept, not deleted: put it back and restore the backup to roll back
	in_c "$c" "if [ -d apps/curtain_roll ]; then rm -rf ../curtain_roll.old && mv apps/curtain_roll ../curtain_roll.old; fi"
done

say "5/5 Assets, migrate, caches, restart"
PUBLIC="$BENCH/apps/kayan_curtain/kayan_curtain/public"
if docker exec "$BACKEND" test -d "$BENCH/sites/assets/curtain_roll" \
	&& ! docker exec "$BACKEND" test -L "$BENCH/sites/assets/curtain_roll"; then
	# assets were real files in the shared volume, not a link - copy the same way
	in_c "$BACKEND" "rm -rf sites/assets/kayan_curtain && cp -r '$PUBLIC' sites/assets/kayan_curtain"
else
	in_c "$BACKEND" "ln -sfn '$PUBLIC' sites/assets/kayan_curtain"
	# old /assets/curtain_roll/... links (Google Images, shared URLs) keep working
	in_c "$BACKEND" "rm -f sites/assets/curtain_roll && ln -sfn '$PUBLIC' sites/assets/curtain_roll"
fi
in_c "$BACKEND" "bench --site '$SITE' migrate"
in_c "$BACKEND" "bench --site '$SITE' clear-cache && bench --site '$SITE' clear-website-cache"
for c in "${CODE_CONTAINERS[@]}"; do docker restart "$c" >/dev/null && echo "restarted $c"; done

say "Done. Check: curl -sI https://<domain>/assets/kayan_curtain/css/curtain.css"
