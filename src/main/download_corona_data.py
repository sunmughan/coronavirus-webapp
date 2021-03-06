import pandas as pd
from pathlib import Path
import os
import sys
import re
from collections import Counter


def set_env():
    curr_wd = os.getcwd()
    if 'Azafar98' in curr_wd:
        if os.path.exists('/home/Azafar98/prod'):
            ENV = 'PROD'
        elif os.path.exists('/home/Azafar98/dev'):
            ENV = 'DEV'
    else:
        ENV = None
    return ENV


ENV = set_env()
if ENV is None:
    RUNNING_LOCALLY = True
else:
    RUNNING_LOCALLY = False


def set_base_file_path(RUNNING_LOCALLY, ENV):
    if RUNNING_LOCALLY:
        return "../../data/json/corona"
    else:
        if ENV.upper() == 'PROD':
            return "/home/Azafar98/prod/coronavirus-webapp"
        elif ENV.upper() == 'DEV':
            return "/home/Azafar98/dev/coronavirus-webapp"
        else:
            raise ValueError("Invalid environment type. Must be 'DEV' or 'PROD'.")


project_home = set_base_file_path(RUNNING_LOCALLY, ENV)
# add your project directory to the sys.path.
# This is purely for PythonAnywhere - not necessary if running locally
if project_home not in sys.path:
    sys.path = [project_home] + sys.path


# This is to redeploy the webapp after the data has been downloaded.
def update():
    os.utime('/var/www/www_covid19-live_co_uk_wsgi.py')


def download_corona_data():
    """
    Get the data straight from the Git repo, since the API has stopped working

    The data is updated once per day, so this function should be run daily.
    :return:
    """

    # Make sure the required path exists. Create it if not.
    # On PythonAnywhere, the paths are a bit different.
    # base_path = set_base_file_path(RUNNING_LOCALLY, ENV)
    if RUNNING_LOCALLY:
        Path(project_home).mkdir(parents=True, exist_ok=True)
        file_path = project_home + '/{}'
    else:
        file_path = project_home + '/data/json/corona'
        Path(file_path).mkdir(parents=True, exist_ok=True)
        file_path = file_path + '/{}'

    confirmed_url = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"
    deaths_url = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"
    recovered_url = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_recovered_global.csv"


    confirmed_data = pd.read_csv(confirmed_url)
    deaths_data = pd.read_csv(deaths_url)
    recovered_data = pd.read_csv(recovered_url)

    # This is necessary so JS doesn't throw errors when trying to graph these later
    def clean_countries(data):
        countries = data.loc[:, 'Country/Region'].tolist()
        bad_chars = ['*', ',', '\'']

        clean_countries_list = []
        for country in countries:
            cleaned_country = ''.join([char for char in country if char not in bad_chars])
            clean_countries_list.append(cleaned_country)

        data['Country/Region'] = clean_countries_list

        return data

    confirmed_data = clean_countries(confirmed_data)
    deaths_data = clean_countries(deaths_data)
    recovered_data = clean_countries(recovered_data)

    # Save the data locally so it doesn't have to be accessed from GitHub every time.
    confirmed_data.to_json(file_path.format("confirmed_cases.txt"))
    deaths_data.to_json(file_path.format("deaths_cases.txt"))
    recovered_data.to_json(file_path.format("recovered_cases.txt"))

    return 0


def aggregate_duplicate_countries(data):
    # This is a weird one. When running on the server, something seems to re-order the columns in the below loop.
    # Then, all the dates are in the wrong order. So save the column order and re-assign it later.
    col_order = data.columns
    countries = data['Country/Region'].tolist()
    count_countries = Counter(countries)
    duplicates = [country for country, count in count_countries.items() if count > 1]

    for duplicate_country in duplicates:
        temp_data = data.loc[data['Country/Region'] == duplicate_country, :]
        temp_data = temp_data.sum(axis=0)
        temp_data['Province/State'] = 'None'
        temp_data['Country/Region'] = duplicate_country

        # Drop all of the old data before inserting the aggregated data
        data = data.loc[data['Country/Region'] != duplicate_country, :]

        temp_data = temp_data.to_frame().T
        data = pd.concat([data, temp_data], axis=0)

    data = data[col_order]

    return data


def get_corona_data():
    """
    Get the data to use for analysis. If it is not saved locally, download it
    :return:
    """
    if RUNNING_LOCALLY:
        file_path = project_home + '/{}'
    else:
        file_path = project_home + '/data/json/corona/{}'

    if not (os.path.exists(file_path.format("confirmed_cases.txt")) or
            os.path.exists(file_path.format("deaths_cases.txt")) or
            os.path.exists(file_path.format("recovered_cases.txt"))):

        print("corona data not downloaded. Downloading.")

        download = download_corona_data()

        if download == 0:
            # Successful download.
            confirmed_df = pd.read_json(file_path.format("confirmed_cases.txt"))
            recovered_df = pd.read_json(file_path.format("recovered_cases.txt"))
            deaths_df = pd.read_json(file_path.format("deaths_cases.txt"))
        else:
            # Download failed
            raise RuntimeError("Data failed to download. Exiting process.")

    else:
        confirmed_df = pd.read_json(file_path.format("confirmed_cases.txt"))
        recovered_df = pd.read_json(file_path.format("recovered_cases.txt"))
        deaths_df = pd.read_json(file_path.format("deaths_cases.txt"))

    return confirmed_df, recovered_df, deaths_df


def update_covid_time_series(data_type):

    confirmed, recovered, deaths = get_corona_data()

    data_type = data_type.upper()

    if data_type == 'CONFIRMED':
        data = confirmed
    elif data_type == 'DEATHS':
        data = deaths
    else:
        data = recovered

    country_data = aggregate_duplicate_countries(data).reset_index(drop=True)

    # Get a list of only the date columns
    date_pat = re.compile('\d{1,2}/\d{1,2}/\d{1,2}')
    cols = country_data.columns.tolist()
    date_cols = [col for col in cols if date_pat.match(col)]

    data = country_data[['Country/Region'] + date_cols].T.reset_index()
    data.columns = data.iloc[0].tolist()
    data = data.drop(0, axis=0)
    data = data.rename(columns={'Country/Region': 'Date'}).reset_index(drop=True)

    data_to_difference = data.loc[:, [col for col in data.columns if col != 'Date']]
    differenced = data_to_difference.diff()
    # First row will be NA values after differencing. Drop that so it doesn't cause problems later when trying to
    # graph the data
    differenced['Date'] = data['Date']
    differenced = differenced.drop(1, axis=0).reset_index(drop=True)

    if RUNNING_LOCALLY:
        file_path = project_home + '/{}'
    else:
        file_path = project_home + '/data/json/corona/{}'

    data.to_json(file_path.format("{}-covid-time-series.txt").format(data_type.lower()))
    differenced.to_json(file_path.format("{}-covid-time-series-diff.txt").format(data_type.lower()))

    return 0


def _run():
    if not RUNNING_LOCALLY:
        download = download_corona_data()
        update_covid_time_series('confirmed')
        update_covid_time_series('deaths')
        update_covid_time_series('recovered')

        if download == 0:
            update()
    else:
        download_corona_data()
        update_covid_time_series('confirmed')
        update_covid_time_series('deaths')
        update_covid_time_series('recovered')

    return 0

_run()