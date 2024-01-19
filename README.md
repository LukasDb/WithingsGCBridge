# Withings to Garmin Connect Bridge
I want to sync my Withings Body Scale with Garmin Connect. However, a direct connection is not possible and the workaround by connecting Withings -> MyFitnessPal -> Garmin Connect does not work reliably for me.
Therefore, i write this script to sync my weight data to GC from Withings using the respective APIs. This is intended to run in a 
Docker container and be scheduled to run by the host system.

## Build
Build the docker image with
```
docker build -t withings-garmin-bridge .
```

## Usage
Run with
```
docker run -e UPDATE_INTERVAL=0 -v /path/to/config:/app -p 5681:5681 --rm withings-garmin-bridge
```
- `-e UPDATE_INTERVAL=0`: disables the automatic update. The script will run once and exit. This is useful for testing or initial registering. The interval time is set in seconds.
- `-v /path/to/config:/app`: /path/to/config should contain the secrets.yaml file as described below and should be writable by the user running the container
- `-p 5681:5681` The port 5681 is used for the local webserver to receive the OAuth callback from Withings.
- `--rm` Remove the container after it exits. All persistent data is saved in /path/to/config

### Behavior
Only new data since the last sync will be uploaded to Garmin. Therefore, just run the program regularly.

## Secrets, Keys etc...
### Withings
1. Create a Withings account, if you don't have one
2. Create a Withings developer account and login to the developer portal. The company name is not important.
3. Create an Application with Public API Integration
4. Target Environment: Development, Name and description are not important. Callback URL: http://127.0.0.1:5681
5. IMPORTANT: Save the client_id and secret in the secrets.yaml as shown below
6. When you run the script for the first time, you will be asked to authorize the application. Follow the instructions in the console.

The used port can be changed, but make sure to change it in the secrets.yaml file and in the Withings Dashboard!

### Garmin Connect
For connecting to Garmin just add your credentials to the secrets.yaml file as described below.

### Secrets.yaml
Generate a secrets.yaml file with the following content:
```
garmin:
  email: <YOUR EMAIL>
  password: <YOUR PASSWORD>
withings:♫
  client_id: <YOUR CLIENT_ID>
  secret: <YOUR SECRET>
  callback_uri: http://127.0.0.1:5681 # this line is optional
```