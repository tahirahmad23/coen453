# Supabase Setup

This project uses Supabase Storage for storing QR code images associated with prescription tokens. 
Before running the token module/functionality, you must manually create the required bucket.

## Steps to Create

1. Go to the [Supabase Dashboard](https://app.supabase.com) and login.
2. Navigate to your project -> **Storage**.
3. Click **Create bucket**.
4. Set the bucket name exactly to: `qr-codes`
5. Check the **Public bucket** toggle (The QR images rely on the unguessable case UUID in the URL).
6. **Save** the bucket.
7. Click on the bucket, then navigate to **Policies**.
8. Create a new policy to allow the `service_role` full access (ALL).
9. Create a new policy to allow `anon` (public) to SELECT (read) the images.

Verify that `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` match your project settings in `.env`.
