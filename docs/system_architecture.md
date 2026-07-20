## Choreo Video Library System Architecture

#### Frontend
The frontend is built with Vite and React. It will let the user upload any dance video file they want and then process the video in the backend. The backend will then return a processed video that will help the user learn the dance better. Features of this app include counts synchronized to the dance video, custom looping and speed, video mirroring, and comparison dances side by side.

### Backend
The backend is built with Flask and handles authentication and video upload. The authentication is handled by adding a new row in Supabase each time a new user is created. When a new video is uploaded, video information is stored in Supabase and the actual video file is stored in Supabase Storage. The video processing is then handled with a thread running in the background so the client does not have to wait too long for the response. After the video processing is finished, the frontend is then notified by Supabase Realtime, allowing for the client to view the processed video.

### Model
The model handles the video processing. (Patrick add to this later)