# ISP router for the labs: forwarding, NAT and DHCP. Replaces `apk add dnsmasq`
# on every deploy, so a deploy no longer needs the internet to bring transport up.
FROM alpine:3.20
RUN apk add --no-cache iproute2 iptables dnsmasq tcpdump iputils
CMD ["sleep", "infinity"]
