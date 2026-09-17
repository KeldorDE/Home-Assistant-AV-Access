DOCKER_COMPOSE=./dev/docker-compose.yml

up:
	docker compose -f ${DOCKER_COMPOSE} up -d

down:
	docker compose -f ${DOCKER_COMPOSE} down

restart: down up

ha-restart:
	docker compose -f ${DOCKER_COMPOSE} restart homeassistant

controller-restart:
	docker compose -f ${DOCKER_COMPOSE} restart av-access-controller
