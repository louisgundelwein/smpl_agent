# LinkedIn Platform Guide

## Authentication

- Login URL: https://www.linkedin.com/login
- Email field: `input#username`
- Password field: `input#password`
- Submit button: `button[type="submit"]` with text "Sign in"
- After login, you land on the feed at https://www.linkedin.com/feed/

## Feed Navigation

- Feed URL: https://www.linkedin.com/feed/
- Posts are in the main feed container, each wrapped in a card element
- Scroll down to load more posts (infinite scroll)
- Each post shows author name, headline, content, and engagement counts
- Post actions: Like, Comment, Repost, Send
- The "..." menu on each post has additional options

## Post Creation

### Text Post
1. Click "Start a post" button on the feed (or the text input area at top of feed)
2. A modal opens with a rich text editor
3. Type your content in the editor
4. Optionally click the image icon to attach media
5. Click "Post" button to publish

### Article (Newsletter/Article)
1. Click "Write article" link below the post creation area
2. Opens the article editor at https://www.linkedin.com/pulse/
3. Add a cover image (optional)
4. Enter title in the headline field
5. Write content in the body editor (supports rich formatting)
6. Click "Publish" to post

### Carousel / Document Post
1. Start a new post (click "Start a post")
2. Click the document icon (looks like a page) in the post toolbar
3. Upload a PDF document
4. Add a title for the document
5. Click "Post" to publish

### Poll
1. Start a new post
2. Click the "+" or "More" icon in the post toolbar
3. Select "Create a poll"
4. Enter the question
5. Add options (2-4)
6. Set duration (1 day, 3 days, 1 week, 2 weeks)
7. Click "Post"

## Profile & Analytics

### Profile Analytics Dashboard
- URL: https://www.linkedin.com/dashboard/
- Shows profile views, post impressions, search appearances
- Click each metric for detailed breakdown

### SSI Score (Social Selling Index)
- URL: https://www.linkedin.com/sales/ssi
- Shows score out of 100 with four components:
  - Establish your professional brand
  - Find the right people
  - Engage with insights
  - Build relationships

### Individual Post Analytics
- Click on the impressions/views count below a post
- Shows detailed breakdown: impressions, reactions, comments, reposts
- Demographics of viewers (job titles, companies, locations)

## Connections & Networking

### Connection Requests
- Visit a profile page
- Click "Connect" button
- Optionally add a note (up to 300 characters)
- Click "Send"

### Accept Connections
- URL: https://www.linkedin.com/mynetwork/invitation-manager/
- Lists pending invitations
- Click "Accept" or "Ignore" for each

### Messaging
- URL: https://www.linkedin.com/messaging/
- Click "New message" or select an existing conversation
- Type message in the composer
- Press Enter or click Send

## Search

### People Search
- URL: https://www.linkedin.com/search/results/people/
- Filter parameters as URL query strings:
  - `keywords=<search term>`
  - `network=["F","S","O"]` (1st, 2nd, 3rd+ connections)
  - `geoUrn=<location ID>`
  - `currentCompany=<company ID>`
  - `title=<job title>`
- Use the filter sidebar for interactive filtering

## Common UI Patterns

### Modals
- LinkedIn uses overlay modals for post creation, messaging, etc.
- Close with X button in top-right or clicking outside
- Confirm dialogs appear for destructive actions (delete, disconnect)

### Dropdowns
- "..." menus open dropdown menus below the trigger
- Select options by clicking the menu item text

### Reactions
- Hover over the Like button to see reaction options (Like, Celebrate, Support, Love, Insightful, Funny)
- Click the desired reaction

### Toast Notifications
- Success/error messages appear as toast notifications at bottom of screen
- They auto-dismiss after a few seconds

## Rate Limiting & Safety

- LinkedIn may show CAPTCHAs or verification prompts for rapid actions
- Keep at least 2 seconds between interactions
- Avoid sending more than ~20 connection requests per day
- Avoid commenting on more than ~30 posts per day
- Profile views are throttled — browsing too fast triggers "unusual activity" warnings

## Account Creation (Signup)
- Signup URL: https://www.linkedin.com/signup
- Fields: first name, last name, email, password
- Submit: "Agree & Join" button
- Email verification: 6-digit code sent to the email address
- Verification field appears on the same page
- Enter code and click "Verify"
- Phone number is optional — try to skip ("Skip" / "Not now")

## CAPTCHA Handling
- CAPTCHAs appear as image challenges or puzzle sliders
- For image CAPTCHAs: identify described objects, click correct tiles
- For text CAPTCHAs: read distorted text and type it
- reCAPTCHA checkbox: just click it
- After 2 failed attempts: abort
