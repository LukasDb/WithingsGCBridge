# Withings to Garmin Connect Bridge
I want to sync my Withings Body Scale with Garmin Connect. However, a direct connection is not possible and the workaround by connecting Withings -> MyFitnessPal -> Garmin Connect does not work reliably for me.
Therefore, i write this script to sync my weight data to GC from Withings using the respective APIs. This is intended to run in a 
Docker container and be scheduled to run by the host system.

Now synchronizes body fat and muscle mass, thanks to @ohshazbot!

## Build
Build the docker image with
```
docker build -t withings-garmin-bridge .
```

## Usage
Run with
```
docker run -e UPDATE_INTERVAL=0 -v /path/to/config:/data -p 5681:5681 --rm withings-garmin-bridge
```
- `-e UPDATE_INTERVAL=0`: disables the automatic update. The script will run once and exit. This is useful for testing or initial registering. The interval time is set in seconds. Additionally, you can set LOG_LEVEL to DEBUG to get more information (default: INFO)
- `-v /path/to/config:/data`: /path/to/config should contain the secrets.yaml file as described below and should be writable by the user running the container
- `-p 5681:5681` The port 5681 is used for the local webserver to receive the OAuth callback from Withings.
- `--rm` Remove the container after it exits. All persistent data is saved in /path/to/config

### Port Change
You can change the port with `-e WITHINGS_PORT=<any unusedport>`. Consequently, you have to change the forwarded port, too: `-p <any unusedport>:<any unusedport>` and you have to change the callback URL in the Withings Developer Portal to the changed port.

### Behavior
- Only new data since the last sync will be uploaded to Garmin. Therefore, just run the program regularly.
- When running for the first time, necessay tokens will be requested from Withings and Garmin. The tokens will be saved in the `.tokenstore` folder. It might be useful to generate the keys on your local system and copy the `secrets.yaml`, the `.tokenstore` folder and the `.last_sync.txt` to your server where the container will be running in the long term.

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


