
# ENV in prod: `.env.prod`
create .env.prod file for loading ENV vars in prod!

During deployment there are many things to consider:
1. .env
2. best is probably copying .env.prod to server and having same copy as both .env and .env.prod -> ENV vars propagate differently via docker-compose, python, within containers or while loading from dot_env / pydantic settings; its pretty complicated!
3. Tricky aspect: mongo stores password/username in permanent storage; therefore if you messed up .env, wrong password will be set and you will have to delete mongo's volume!



# HTTPS: TODO: Lets Encrypt email

Hi,

As a Let’s Encrypt Subscriber, you benefit from access to free, automated TLS certificates. One way we have supported Subscribers is by sending expiration notification emails when it’s time to renew a certificate.

We’re writing to inform you that we intend to discontinue sending expiration notification emails. You can learn more in this blog post:

https://letsencrypt.org/2025/01/22/Ending-Expiration-Emails

Here are some actions you can take today:

Automate with an ACME Client that supports Automated Renewal Information (ARI). ARI enables us to automatically renew your certificates ahead of schedule should the need arise:

https://letsencrypt.org/2024/04/25/guide-to-integrating-ari-into-existing-acme-clients

Sign up for a third-party monitoring service that may provide expiration emails. We can recommend Red Sift Certificates Lite, which provides free expiration emails for up to 250 active certificates:

https://redsift.com/pulse-platform/certificates-lite

Opt in to emails. While we are deprecating expiration notification emails, you can opt in to continue to receive other emails. We’ll keep you informed about technical updates, and other news about Let’s Encrypt and our parent nonprofit, ISRG, based on the preferences you choose:

https://letsencrypt.org/opt-in/

