DOCKER_COMPOSE=./dev/docker-compose.yml

up:
	docker compose -f ${DOCKER_COMPOSE} up -d --build

down:
	docker compose -f ${DOCKER_COMPOSE} down

restart: down up

logs:
	docker compose -f ${DOCKER_COMPOSE} logs -f

emulator-logs:
	docker compose -f ${DOCKER_COMPOSE} logs -f matrix-emulator

# Returns the emulated matrix to its factory state.
emulator-reset:
	printf 'RESET\r\n' | nc localhost 2323
