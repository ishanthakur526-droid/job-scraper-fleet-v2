# Cloud mode: no installation, results on a web page

GitHub can run JobFleet for you every weekday, for free, and publish the results as a web page that works on your phone. You need a free GitHub account; nothing is installed on your computer.

## Set it up (about 5 minutes)

1. **Copy the project.** Open <https://github.com/ishanthakur526-droid/jobfleet>, click the green **Use this template** button → **Create a new repository**. Give it any name (for example `my-jobs`) and click **Create repository**.
2. **Switch on the web page.** In your new repository: **Settings** → **Pages** (left menu) → under *Build and deployment*, set **Source** to **GitHub Actions**. Nothing else to click.
3. **Fill in the form.** Go to the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**. Choose **Set up my profile** on the left → **Run workflow** (right side), fill in:
   - *Country or countries*: e.g. `Germany`, or `United States, Canada`
   - *Cities* (optional): e.g. `Berlin, Munich`
   - *Remote jobs*: include / only / exclude
   - *Years of work experience*: e.g. `2`
   - *Kind of job*, plus up to two more
   - *More job titles* (optional): e.g. `Power BI Developer, Pricing Analyst`

   and press the green **Run workflow** button.
4. **Wait about 5 minutes.** The form saves `profile.toml` in your repository and starts **Find jobs**. When its run shows a green tick, your page is at:

   `https://<your-github-username>.github.io/<repository-name>/`

   (also linked on the run's page next to *publish*).

From then on **Find jobs** runs every weekday at 10:30 UTC. To run it right now: **Actions → Find jobs → Run workflow**.

## Change your search

- Run **Set up my profile** again with new answers, or
- open `profile.toml` in your repository, click the pencil icon, edit, and **Commit changes**. The [customisation guide](CUSTOMIZE.md) explains every line.

To add companies, edit `my_companies.txt` the same way (one careers link per line).

## Download the CSV files

Each **Find jobs** run keeps the CSV files for 14 days: open the run and download **jobfleet-results** under *Artifacts*.

## Privacy

- On a free GitHub account, Pages sites are **public**. Anyone with the address can see the page: the job postings found and the summary of your search (for example "Marketing | United Kingdom | 0-3 years"). It contains nothing else about you, and the address is not listed anywhere unless you share it.
- Your repository is public too (needed for free Pages). Do not put personal details into `profile.toml`: a `name` like "My search" is enough.
- Prefer full privacy? Run JobFleet on your own computer instead (see the README), where everything stays local.

## Good to know

- **AI features are off in the cloud**, because Claude Code needs your personal login. Run it locally to use them.
- **A few career sites may refuse GitHub's servers** or be down for maintenance. The dashboard's **Sources** tab shows what worked on each run.
- **"New today"** relies on remembered history, which GitHub keeps between runs (as a cache). If the cache expires, for example after a week without runs, every job shows as new once.
- Scheduled runs pause after 60 days without any activity in the repository (a GitHub rule). Any commit, or running **Find jobs** by hand, restarts them.
- GitHub Actions is free for public repositories; this uses a few minutes per day.
