# Instagram Platform Guide

## Authentication

- Login URL: https://www.instagram.com/accounts/login/
- Username field: `input[name="username"]`
- Password field: `input[name="password"]`
- Submit button: `button[type="submit"]` with text "Log in"
- After login, you land on the home feed at https://www.instagram.com/
- 2FA: may prompt for SMS/authenticator code — enter in the verification field and click "Confirm"
- "Save Your Login Info?" prompt: click "Not Now" to skip

## Feed Navigation

- Home feed URL: https://www.instagram.com/
- Posts appear as cards with image/video, author, likes, caption
- Scroll down to load more posts (infinite scroll)
- Each post shows: author avatar + username, image/video, like count, caption preview, comment count
- Post actions: like (heart icon), comment (speech bubble), share (paper plane), save (bookmark)

## Explore & Hashtag Pages

- Explore URL: https://www.instagram.com/explore/
- Grid of recommended posts (photos/reels)
- Hashtag page URL: https://www.instagram.com/explore/tags/{hashtag}/
- Shows top posts and recent posts for the hashtag
- Reels tab: https://www.instagram.com/reels/

## Post Creation (Web Interface)

### Photo Post
1. Click the "+" (create) icon in the top navigation bar
2. Select "Post" from the dropdown
3. Click "Select from computer" or drag/drop an image
4. Click "Next" to go to the editing screen (filters, crop)
5. Click "Next" again to go to the caption screen
6. Enter caption text in the caption field
7. Optionally add location by clicking "Add location"
8. Click "Share" to publish

### Carousel Post (Multiple Images)
1. Click the "+" icon → "Post"
2. Click the multi-select icon (overlapping squares) in the file picker
3. Select multiple images (up to 10)
4. Click "Next" → adjust each image if needed
5. Click "Next" → enter caption
6. Click "Share"

### Reel
1. Click the "+" icon → "Reel"
2. Upload a video file
3. Add cover image, trim if needed
4. Click "Next" → enter caption, add hashtags
5. Click "Share"

## Story Creation

1. Click the "+" icon → "Story" OR click your profile picture with the "+" badge
2. Upload an image/video from computer
3. Add text, stickers, or drawings using the toolbar
4. Click "Share to Story" or "Your Story" to publish
5. Stories disappear after 24 hours

## Comments & Replies

- Click the speech bubble icon on a post to view/add comments
- Comment box is at the bottom of the comments section
- Type comment and press Enter or click "Post"
- To reply to a comment: click "Reply" under the comment, type, submit
- Replies are nested under the parent comment

## Likes

- Click the heart icon below a post to like
- Heart turns red when liked
- Double-tap on the post image to like
- Click red heart again to unlike

## Direct Messages (DMs)

- DM inbox: click the messenger/paper-plane icon in the top nav
- URL: https://www.instagram.com/direct/inbox/
- To compose: click the pencil/new-message icon
- Search for a username, select them
- Type message and press Enter or click "Send"

## Follow / Unfollow

### Follow
- Go to a user's profile page: https://www.instagram.com/{username}/
- Click the "Follow" button
- Button changes to "Following"

### Unfollow
- Go to the user's profile
- Click "Following" button
- Select "Unfollow" from the confirmation prompt

## Profile & Analytics

### Profile Page
- URL: https://www.instagram.com/{username}/ or own profile via avatar
- Shows: posts count, followers count, following count
- Bio, profile picture, highlights

### Insights (Business/Creator Accounts)
- Tap "Professional dashboard" or "Insights" on profile
- Shows: accounts reached, accounts engaged, total followers
- Individual post insights: impressions, reach, likes, comments, saves, shares

## Search

- Click the search (magnifying glass) icon
- Type query → results show accounts, tags, places
- URL: https://www.instagram.com/explore/search/
- Filter by: Accounts, Tags, Places

## Followers / Following Lists

- Profile page → click "followers" count → scrollable list
- Profile page → click "following" count → scrollable list
- Each entry has username and "Follow"/"Following" button

## Rate Limiting & Safety

- Instagram is VERY strict about automated behavior
- Keep at least 5 seconds between interactions (default delay)
- New accounts are heavily restricted
- Too many follows/unfollows trigger temporary blocks (action blocked for 24-48h)
- Daily limits (approximate):
  - Follows: ~50-100/day for new accounts, ~200 for established
  - Likes: ~100-300/day
  - Comments: ~50-100/day
  - DMs: ~50-80/day
- Suspicious login handling: "We detected an unusual login attempt" → verify via email/SMS
- CAPTCHA may appear during login or signup

## Account Creation (Signup)

- Signup URL: https://www.instagram.com/accounts/emailsignup/
- Fields: email/phone, full name, username, password
- Click "Sign up"
- Email verification code is sent → enter code and click "Confirm"
- Birthday prompt → enter and click "Next"
- May require phone number verification
- Profile photo suggestion → click "Skip"

## CAPTCHA Handling

- reCAPTCHA checkbox or image challenges may appear
- During signup, login, or after suspicious activity
- After 2 failed attempts: abort and report

## Common UI Patterns

### Web Interface
- Top navigation: home, search, explore, reels, messages, notifications, create, profile
- Modal dialogs for post creation, confirmations
- Toast notifications for success/error
- "Action Blocked" popup when rate limited

### Confirmation Dialogs
- Delete post: "Delete post?" modal with "Delete" and "Cancel"
- Unfollow: "Unfollow {username}?" confirmation
- Discard post: "Discard post?" if navigating away during creation
