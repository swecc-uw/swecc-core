# SWECC Rabbit 🐇

Message broker for SWECC

## Setting up a management user (for observability)

You can use the default login (username: `guest`, password: `guest`) to log in, but the preferred way is to create your own user (see below).

### Creating Your Own User
1. `docker exec -it rabbitmq bash` - Exec into the docker container
2. `rabbitmqctl add_user [username] [password]` - Add a user
3. `rabbitmqctl set_permissions_globally [username] ".*" ".*" ".*"` - Give user all read/write permissions to all hosts
4. `rabbitmqctl set_user_tags [username] monitoring` - Give user permissions to access the RabbitMQ management portal at `http://[hostname]:15672`
