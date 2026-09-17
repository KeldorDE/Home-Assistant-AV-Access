DOCKER_COMPOSE=./dev/docker-compose.yml

up:
	docker compose -f ${DOCKER_COMPOSE} up -d

down:
	docker compose -f ${DOCKER_COMPOSE} down

restart: down up

logs:
	docker compose -f ${DOCKER_COMPOSE} logs -f
