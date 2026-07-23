## Choreo Video Library System Architecture

#### Frontend
The frontend is built with Vite and React. After authentication, it will let the user upload any dance video file they want and then process the video in the backend. The backend will then return a processed video that will help the user learn the dance better. Features of this app include counts synchronized to the dance video, custom looping and speed, video mirroring, and comparison dances side by side.

Here is a preview of the frontend file architecture. 

```
src/
├── pages/
│   ├── Auth.css
│   ├── Auth.jsx          # Authentication page (starting page for user)
│   ├── Home.css
│   ├── Home.jsx          # Home page, where the user can access the app features such as counts synchronized to the dance video
│   ├── UploadDance.css
│   └── UploadDance.jsx   # Upload dance page, where the user uploads a dance video of their choice
├── App.jsx
├── index.css
├── main.jsx              # App entry point
```


### Backend
The backend is built with Flask and handles authentication and video upload. Authentication is handled by Supabase Auth. When a user signs in or signs up, the Flask backend calls Supabase's sign-up/sign-in API. The email verification is handled with a custom SMTP (Resend) to avoid Supabase rate limiting. When a new video is uploaded, video information is stored in Supabase and the actual video file is stored in Supabase Storage. The video processing is then handled with a thread running in the background so the client does not have to wait too long for the response. After the video processing is finished, the frontend is then notified by Supabase Realtime, allowing for the client to view the processed video.

### Model
The model handles the video processing. (Patrick add to this later)
