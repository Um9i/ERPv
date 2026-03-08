dev:
	podman compose up --build

prod:
	podman compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
