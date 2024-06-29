import os
import flask
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaIoBaseUpload
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from io import BytesIO

# Configuration
CLIENT_SECRETS_FILE = "gdrive.json"
SCOPES = ['https://www.googleapis.com/auth/drive']
API_SERVICE_NAME = 'drive'
API_VERSION = 'v3'
MONGODB_URI = "mongodb+srv://sai:8778386853@cluster0.9vhjs.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "flask_app"
COLLECTION_NAME = "google_drive_tokens"

# Initialize Flask app
app = flask.Flask(__name__)
app.secret_key = 'REPLACE_ME'

# Initialize MongoDB client
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

@app.route('/')
def index():
    return flask.render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    credentials = get_credentials()
    if not credentials:
        return flask.redirect(flask.url_for('authorize'))

    drive = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

    # Check if the folder exists, if not create it
    folder_id = get_folder_id(drive, 'root')  # Use 'root' for root folder of Google Drive
    if not folder_id:
        folder_metadata = {'name': 'MyUploads', 'mimeType': 'application/vnd.google-apps.folder'}
        folder = drive.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
    

    # Handle file upload directly to Google Drive
    uploaded_file = flask.request.files['file']
    if uploaded_file.filename == '':
        return 'No selected file'

    file_metadata = {'name': secure_filename(uploaded_file.filename), 'parents': [folder_id]}
    media = MediaIoBaseUpload(BytesIO(uploaded_file.read()), mimetype=uploaded_file.content_type)

    try:
        print('uploading file',uploaded_file.filename)
        
        drive.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print('uploading file',uploaded_file.filename)
        save_credentials(credentials)
        return flask.jsonify({'message': 'File uploaded successfully'})
    except Exception as e:
        print('uploading file',uploaded_file.filename,'error')
        print(f"Error uploading file to Google Drive: {e}")
        return flask.jsonify({'error': 'Upload failed'}), 500

@app.route('/authorize')
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    flask.session['state'] = state
    return flask.redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = flask.session['state']
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    flow.fetch_token(authorization_response=flask.request.url)
    credentials = flow.credentials

    # Save credentials to MongoDB
    save_credentials(credentials)

    return flask.redirect(flask.url_for('index'))

def get_folder_id(drive, folder_name):
    results = drive.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                                 spaces='drive',
                                 fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    return None

def save_credentials(credentials):
    credentials_dict = credentials_to_dict(credentials)
    existing_token = collection.find_one()
    if existing_token:
        collection.update_one({}, {"$set": credentials_dict})
    else:
        collection.insert_one(credentials_dict)

def get_credentials():
    token_data = collection.find_one()
    if token_data:
        credentials = google.oauth2.credentials.Credentials(
            token_data['token'],
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
        return credentials

    return None

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }


if __name__ == '__main__':
    import os 
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  
    app.run('localhost', 8080, debug=True)
