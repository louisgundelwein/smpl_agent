# Reddit Platform Guide

## Authentication

- Login URL: https://www.reddit.com/login
- Username field: `input#loginUsername`
- Password field: `input#loginPassword`
- Submit button: `button[type="submit"]` with text "Log In"
- After login, you land on the home feed at https://www.reddit.com/

## Feed Navigation

- Home feed URL: https://www.reddit.com/
- Sort options: hot, new, top, rising (as URL path or tab buttons)
- Posts are in the main feed container, each as a card or compact row
- Scroll down to load more posts (infinite scroll)
- Each post shows: title, author (u/username), subreddit (r/name), upvotes, comments count
- Post actions: upvote/downvote arrows, comment icon, share, save, awards

## Subreddit Navigation

- Subreddit URL: https://www.reddit.com/r/{subreddit}/
- Sort tabs: Hot, New, Top, Rising
- Join button visible in the subreddit header (changes to "Joined" after joining)
- Sidebar has subreddit rules, description, member count
- Submit URL: https://www.reddit.com/r/{subreddit}/submit

## Post Creation

### Text Post
1. Go to subreddit submit page: https://www.reddit.com/r/{subreddit}/submit
2. Select the "Text" or "Post" tab
3. Enter a title in the title field
4. Write body text in the text editor (supports markdown)
5. Optionally select a flair from the flair dropdown
6. Click "Post" to submit

### Link Post
1. Go to subreddit submit page
2. Select the "Link" tab
3. Enter a title
4. Paste the URL in the URL field
5. Click "Post"

### Image/Video Post
1. Go to subreddit submit page
2. Select the "Images & Video" tab
3. Enter a title
4. Upload the image/video file
5. Click "Post"

### Poll
1. Go to subreddit submit page
2. Select the "Poll" tab
3. Enter a title (the question)
4. Add options (2-6 choices)
5. Set poll duration (1-7 days)
6. Click "Post"

### Crosspost
1. On the original post, click "..." or "Share"
2. Select "Crosspost"
3. Choose target subreddit
4. Edit title if desired
5. Click "Post"

## Comments & Replies

- Click on a post to open the comments page
- Comment box is at the top of the comments section
- Type comment and click "Comment" button
- To reply to a comment: click "Reply" under the comment
- Nested reply threads are indented

## Voting

- Upvote: click the up arrow (turns orange when active)
- Downvote: click the down arrow (turns blue when active)
- Click again to un-vote
- Score is displayed between the arrows

## Messaging

### Send DM
- URL: https://www.reddit.com/message/compose/?to={username}
- Fill in recipient (u/username), subject, and body
- Click "Send"

### Inbox
- URL: https://www.reddit.com/message/inbox/
- Tabs: All, Unread, Messages, Comment Replies, Post Replies
- Click message to expand/read

## Subreddit Management

### Join
- Navigate to subreddit page
- Click "Join" button in the header
- Button changes to "Joined"

### Leave
- Navigate to subreddit page
- Click "Joined" button (hover shows "Leave")
- Confirms leaving

### My Subreddits
- URL: https://www.reddit.com/subreddits/mine/
- Lists all subscribed subreddits

## Profile & Karma

### Profile Page
- URL: https://www.reddit.com/user/{username}/ or https://www.reddit.com/user/me/
- Shows: post karma, comment karma, total karma, account age
- Tabs: Overview, Posts, Comments, Saved

### Karma Breakdown
- Visible on profile page
- Post karma: earned from post upvotes
- Comment karma: earned from comment upvotes

## Search

- Search URL: https://www.reddit.com/search/?q={query}
- Within subreddit: https://www.reddit.com/r/{subreddit}/search/?q={query}&restrict_sr=1
- Sort options: Relevance, Hot, Top, New, Most Comments
- Filter by time: Hour, Day, Week, Month, Year, All

## Common UI Patterns

### New Reddit (Redesign)
- Card-based layout by default
- Modals for some actions (login, some settings)
- Dropdown menus under "..." buttons

### Confirmation Dialogs
- Delete post/comment: "Are you sure?" modal
- Leave subreddit: confirmation prompt

### Toast Notifications
- Success/error toasts appear at bottom of screen
- Auto-dismiss after a few seconds

## Rate Limiting & Safety

- Reddit is strict about automated behavior
- Keep at least 3 seconds between interactions
- New accounts have posting restrictions (karma/age requirements per subreddit)
- Too many actions trigger CAPTCHA or temporary bans
- Avoid more than ~10 posts per day on new accounts
- Comment cooldowns apply to new/low-karma accounts (1 comment per 10 minutes)
- Some subreddits require minimum karma to post

## Account Creation (Signup)

- Signup URL: https://www.reddit.com/register
- Fields: email, then username and password on next step
- Email verification may be required
- CAPTCHA is common during signup (reCAPTCHA or image-based)
- Phone verification is sometimes required and cannot always be skipped

## CAPTCHA Handling

- reCAPTCHA checkbox: click it, may trigger image challenges
- Image CAPTCHAs: select matching images (traffic lights, crosswalks, etc.)
- After 2 failed attempts: abort and report
