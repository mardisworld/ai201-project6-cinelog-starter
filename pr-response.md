# PR Response Doc — CineLog Watchlist Feature

## AI Usage
1. I asked AI: Can you explain the project structure's flow? Looking at app.py, I don't see it calling watchlist_service.py or collection_service.py. How does the app start?

This is the response I got back from Claude:

Great question — and the answer is that app.py never calls the services directly, and it's not supposed to. This is a classic layered Flask architecture where each layer only talks to the one directly below it. Here's the shape:

The layers

app.py                    ← application factory: wires everything together
  │  registers blueprints
  ▼
routes/*.py               ← HTTP layer: URLs, request parsing, status codes
  │  calls service functions
  ▼
services/*_service.py     ← business logic: rules, validation, dedup
  │  queries/commits via
  ▼
models.py + db            ← data layer: SQLAlchemy models & the database
The services are called by the routes, not by app.py. That's the link you were missing.

How the app actually starts
Entry point — app.py:37–39. Running python app.py hits the if __name__ == "__main__": block, which calls create_app() and then app.run(debug=True). (In tests, create_app(config=...) is called instead — same factory, different config.)

The factory builds the app — create_app():

Creates the Flask app and sets config (DB URL, secret key) — lines 11–19
db.init_app(app) binds the shared SQLAlchemy instance (defined at app.py:7) to this app — line 21
Imports and registers the three blueprints — lines 23–29. This is where the route modules get connected, each under a URL prefix:
films_bp → /films
collection_bp → /collection
watchlist_bp → /watchlist
db.create_all() creates any missing tables — line 32
Blueprints pull in the services — when app.py imports a route module, that module imports its service at the top. For example routes/collection.py:8–14 imports add_to_collection, remove_from_collection, etc. So the service does get loaded — transitively, through the route module, not through app.py.

2. I also encountered errors when running Flask.

![alt text](<instance/images/flask error.png>)

AI  helped me to resolve the errors so I could test the endpoints.

3. When I moved to correct the test file, I received this error.

![alt text](<instance/images/testing errros.png>)

Somehow the changes I had made to change add_to_watchlist() had been reverted to save_to_watchlist(). Claude helped me identify the error and fix them.

4. For the comment that PR reviewer left, I gave Claude the following prompt to receive help to make an informed decision on whether the watchlist model default should be set to true or false.

```
For class, class WatchlistEntry(db.Model):
    """Represents a film a user wants to watch (saved for later)."""
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=False)
    film_id = db.Column(db.Integer, db.ForeignKey("film.id"), nullable=False)
    date_added = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    public = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "film_id": self.film_id,
            "date_added": self.date_added.isoformat(),
            "public": self.public,
        },

PR Reviewer wants to know why watchlists default to public=True. We don't have a documented decision on default visibility for user lists. He wants me to add a note to your PR description explaining my reasoning. He wants to make sure we're being intentional here, not just inheriting a default. If you think about it and think that public should=False, say so but document your decion-making. Just consider the question and decide which option is best, and explain your reasoning.
```

I did not have a good answer, so I asked it to consider the question and provide its reasoning. I agreed with the its reasoning, so I changed the default watchlist model public=False and included its responses, unedited,here in this document. .


Watchlist entries should default to `public=False` (private). I changed the model default from `True` to `False`.

## Comment 1 — Rename

**What I did:**

As suggested by the PR reviewer, I changed the name of save_to_watchlist() to add_to_watchlist(). I also changed the references to this function throughout the repository, so that I could test the endpoints.

**How I verified:**

I submitted a post request with a film id in body and user id in url to add a film_id to user's watchlist.

![alt text](instance/images/add_to_watchlist.png)

I then verified that it was in user's watchlist:

![alt text](<instance/images/users watchlist.png>)


## Comment 2 — Deduplication
**What I did:**

I added in an AlreadyInWatchlistError in watchlist_service.py, imported it in to watchlist.py, and added a try except block to catch FilmNotFoundError and AlreadyInWatchlistError in same file.

**How I verified:**

I sent a post request to endpoint to add to user's watchlist, then sent again and received this error message back.

![alt text](<instance/images/already in watchlist.png>)

## Comment 3 — Missing test
**What I did:**

Added condition to existing text that if FilmNotFoundError was raised, the film was not persisted to database.

**How I verified:**

I ran tests and verified that they are all passing.
![alt text](<instance/images/tests passed.png>)


## Comment 4 — Default visibility

**My position:**
Watchlist entries should default to public=False (private).

**Reasoning:**

Reasoning: The cost of the two possible wrong defaults is asymmetric — a wrongly-public list leaks personal data irreversibly, while a wrongly-private list costs the user one click to share. Watchlist data is intent data (what someone wants to watch), which can be sensitive. Privacy-by-default is also the regulatory/industry norm (GDPR Art. 25): sharing personal data should be opt-in, not opt-out. public=True reads as an inherited default rather than an intentional choice.

**Tradeoff acknowledged:**

If CineLog is meant to be social/discovery-first, private-by-default adds friction to sharing. I accept this because sharing can be enabled later via explicit opt-in, whereas trust lost from leaking data by default cannot be recovered.

## Comment 5 — Sort order

**My position:**

I agree with the reviewer. I changed `get_watchlist()` to sort by `date_added` descending (most recently added first) instead of alphabetically by title. Previously it used `.order_by(Film.title.asc())`; it now uses `.order_by(WatchlistEntry.date_added.desc())`. I made the following changes to the codebase:

**models.py**
I added a film relationship to WatchlistEntry.
film = db.relationship("Film", backref="watchlist_entries", lazy=True)

**services/watchlist_service.py**

Sort order changed from Film.title.asc() → WatchlistEntry.date_added.desc(), so get_watchlist now returns most recently added first (matching get_collection's behavior). Docstring updated to say so.

**tests/test_collection.py**
I added test_get_watchlist_returns_newest_first, mirroring the collection sort test: two entries with different date_added, asserting the newer one (Blade Runner) comes first.

**Reasoning:**

A watchlist is a running list of "things I just decided I want to watch," so recency matches how people actually use it — the film you added a minute ago is the one you're most likely thinking about, and it should be at the top rather than buried wherever it falls alphabetically. This also makes the watchlist consistent with the collection: `get_collection()` already returns newest-first, so both of a user's lists now behave the same way, which is less surprising. Alphabetical order is really only helpful for *looking something up* in a long list, which is a secondary use case and can be handled later with an explicit sort control if users ask for it.

**Engagement with reviewer's point:**

The reviewer's reasoning — "most users want to see what they added recently" — is exactly right and is the deciding factor here, so I didn't see it differently. The one nuance worth noting for the future is that recency-first is the best *default*, not necessarily the only option: for very long watchlists an alphabetical or filterable view could be a useful opt-in later. But as a default we're aligned, and the decision is now documented and implemented.

**How I verified:**

I updated `test_get_watchlist_returns_newest_first` (mirroring the existing collection sort test): it adds two entries with different `date_added` timestamps and asserts the newer one comes back first. All tests pass.

## Comment 6 — Rebase
**What conflicted:**

One file that had a conflict was .gitignore, prresponse.md, watchlist.py, models.py, test_collection.py,

This was awful. I had already resolved the UUID problem before beginning the rest of the fixes, so this might have caused more errors than if i had not done that, but performing:

git fetch origin and

git rebase origin/main

led to a host of issues. I don't remmeber all of them, and I don't have all of them in my terminal history.

Some of the errors I encountered:

```
(.venv) (base) marissastaller@Marissas-MBP ai201-project6-cinelog-starter % git status
interactive rebase in progress; onto bbe206c
Last commands done (3 commands done):
   pick 7c37bcd fix: update film retrieval method to use db.session.get in collection and watchlist services
   pick d9efe37 added .gitignore and template for prresponse.md
  (see more in file .git/rebase-merge/done)
Next commands to do (7 remaining commands):
   pick 2d40c95 chore: fixed merge conflict for .gitignore
   pick 7fd982b fix: somehow I deleted my pr-response initial entry, so I rewrote it. I also added back in the models section that had gotten accidentally deleted.
  (use "git rebase --edit-todo" to view and edit)
You are currently editing a commit while rebasing branch 'feature/watchlist-v2' on 'bbe206c'.
  (use "git commit --amend" to amend the current commit)
  (use "git rebase --continue" once you are satisfied with your changes)

```

```
nothing to commit, working tree clean
(.venv) (base) marissastaller@Marissas-MBP ai201-project6-cinelog-starter % git checkout feat
ure/watchlist-v2
Warning: you are leaving 3 commits behind, not connected to
any of your branches:

  bde04e0 chore: fixed merge conflict
  c8064e4 fix: update film retrieval method to use db.session.get in collection and watchlist services
  1ac4852 added watchlist model and endpoint fixed a bug more changes

If you want to keep them by creating a new branch, this may be a good time
to do so with:

 git branch <new-branch-name> bde04e0

Switched to branch 'feature/watchlist-v2'
```

```
Last commands done (3 commands done):
   pick 7c37bcd fix: update film retrieval method to use db.session.get in collection and watchlist services
   pick d9efe37 added .gitignore and template for prresponse.md
  (see more in file .git/rebase-merge/done)
Next commands to do (7 remaining commands):
   pick 2d40c95 chore: fixed merge conflict for .gitignore
   pick 7fd982b fix: somehow I deleted my pr-response initial entry, so I rewrote it. I also added back in the models section that had gotten accidentally deleted.
  (use "git rebase --edit-todo" to view and edit)
You are currently editing a commit while rebasing branch 'feature/watchlist-v2' on 'bbe206c'.
  (use "git commit --amend" to amend the current commit)
  (use "git rebase --continue" once you are satisfied with your changes)
  ```

  ```
  You are not currenty on a branch.
  ```

  Some of the commands I tried:

  ```
git log --oneline -n1 # Copy the latest commit hash
git checkout main
git merge <commit-hash>
  ```

```
# Correct way to create and switch to a new branch from current branch
git checkout -b feature/watchlist-v2
git switch feature/watchlist-v2
git fetch origin
git switch -c watchlist-v2 origin/watchlist-v2
```

Created a new branch when it said:

```
 bde04e0 chore: fixed merge conflict
c8064e4 fix: update film retrieval method to use db.session.get in collection and watchlist services
1ac4852 added watchlist model and endpoint fixed a bug more changes

If you want to keep them by creating a new branch, this may be a good time
to do so with:

git branch <new-branch-name> bde04e0

```

My branch never showed up in my GitHub repository.


**How I resolved it:**

Eventually, I gave up and asked Claude and Copilot to resolve my GitHub problmems.

Here are some of the commands it ran for me:

git diff --check

git diff --name-only --diff-filter=U

git status --short

git add pr-response.md && GIT_EDITOR=true git rebase --continue

grep -R "order_by" -n services/watchlist_service.py services/collection_service.py

GIT_EDITOR=true git rebase --continue

git rebase --quit

.venv/bin/python -m pytest tests/test_collection.py

git log --oneline --decorate -5

**How I verified no conflict remains:**

This is what my Git commit history looked like before cleanup.

![alt text](<instance/images/commit history before cleanup.png>)

When I ran the two commands given in the assignment,

```
git log --oneline origin/main..HEAD
git rebase -i HEAD~N
```

I couldn't type into the "editor" at all. So the commit history looks terrible, but I will try to use AI to fix it.

Prompt:



## PR Description
<!-- Written at the end — feature overview, design decisions, manual testing steps -->