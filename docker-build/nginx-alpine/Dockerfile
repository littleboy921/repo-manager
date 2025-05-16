FROM nginx:1.23.2-alpine
RUN apk add --no-cache fcgiwrap && \
    apk add --no-cache git-daemon 
COPY start.sh /start.sh
CMD [ "/bin/sh","/start.sh","-DFOREGROUND" ]
