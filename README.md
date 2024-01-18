# Withings to Garmin Connect Bridge
I want to sync my Withings Body Scale with Garmin Connect. However, a direct connection is not possible and the workaround by connecting Withings -> MyFitnessPal -> Garmin Connect does not work reliably for me.
Therefore, i write this script to sync my weight data to GC from Withings using the respective APIs. This is intended to run in a Docker container and be scheduled to run by the host system.

## Secrets, Keys etc...
### Withings
1. Create a Withings account, if you don't have one
2. Create a Withings developer account and login to the developer portal. The company name is not important.
3. Create an Application with Public API Integration
4. Target Environment: Development, Name and description are not important. Callback URL: http://127.0.0.1:5000
5. IMPORTANT: Save the client_id and secret in the secrets.yaml as shown below

The used port can be changed, but make sure to change it in the secrets.yaml file and in the Withings Dashboard!

### Garmin Connect
For connecting to Garmin just add your credentials to the secrets.yaml file as described below.

### Secrets.yaml
Generate a secrets.yaml file with the following content:
```
garmin:
  email: <YOUR EMAIL>
  password: <YOUR PASSWORD>
withings:
  client_id: <YOUR CLIENT_ID>
  secret: <YOUR SECRET>
  callback_uri: http://127.0.0.1:5000 # this line is optional
```