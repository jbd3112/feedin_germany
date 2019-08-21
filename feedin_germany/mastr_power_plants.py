# -*- coding: utf-8 -*-
"""
The `mastr_power_plant` module contains functions for downloading and
processing renewable power plant data for Germany from the
Markstammdatenregister (MaStR). todo source orginial + OEP

# todo: opsd_power_plants.py and this module are from different origins. However,
# there are similar or even the same functionalities used. It could be possible
# to first load the respective register and then carry out the functions.

"""

__copyright__ = "Copyright oemof developer group"
__license__ = "GPLv3"

# imports
import pandas as pd
import os

from windpowerlib import get_turbine_types

# internal imports
from feedin_germany import power_plant_register_tools as ppr_tools
from feedin_germany import database_tools as db_tools
from feedin_germany import opsd_power_plants as opsd
import settings


def load_mastr_data_from_oedb():
    """
    Loads the MaStR power plant units ...

    Notes
    -----
    todo: use sessionmaker um Anlagen auszuwählen ??
    then todo: login and token need to be adapted/automatized
         todo: possible --> engine creation as separate function

    Returns
    -------


    """

    table_name = 'bnetza_mastr_wind_v1_4_clean'
    register = db_tools.load_data_from_oedb_with_oedialect(
        schema='sandbox', table_name=table_name)
    return register


def helper_load_mastr_from_file(category):
    r"""
    todo remove when loaded from oedb

    only for 50 Hertz

    Notes
    -----
    - Manche "Bruttoleistungen" scheinen falsch zu sein: 0 oder krumme Zahl.

    Parameters
    ----------
    category : string
        Energy source category for which the register is loaded. Options:
        'Wind', ... to be added.

    Returns
    -------

    """
    settings.init()
    if category == 'Wind':
        filename = os.path.join(
            settings.path_mastr_wind,
            'bnetza_mastr_wind_v1_4_clean_50hertz.csv')
        usecols = [
            'Nabenhoehe', 'Rotordurchmesser',
            # 'HerstellerName', 'Einheitart', 'Einheittyp', 'Technologie',
            # 'Energietraeger',
            'Typenbezeichnung', 'Laengengrad', 'Breitengrad',
            'Inbetriebnahmedatum', 'DatumEndgueltigeStilllegung',
            'DatumBeginnVoruebergehendeStilllegung',
            'DatumWiederaufnahmeBetrieb', 'Lage', 'InstallierteLeistung',
            'Seelage', 'lat', 'lon'
                ]
    elif category == 'Solar':
        raise ValueError("Solar MaStR data not added, yet.")
    else:
        raise ValueError("Category {} not existent. ".format(category) +
                         "Choose from: 'Wind', ...") # todo add
    try:
        mastr_data = pd.read_csv(filename, sep=',', encoding='utf-8',
                                 header=0, usecols=usecols)
    except FileNotFoundError:
        raise FileNotFoundError("Check MaStR file location.")
    return mastr_data


def prepare_mastr_data(mastr_data, category):
    r"""
    Pre-processing of MaStR data.

    - translation to english
    - short cuts

    - decom, com month etc. as in opsd
    - remove rows with nans

    possible
    - remove pp with missing coordinates
    -


    Parameters
    ----------
    mastr_data : pd.DataFrame
        Contains raw MaStR data as loaded in
        `:py:func:helper_load_mastr_from_file`. # todo adapt
    category : string
        Energy source category for which the register is loaded. Options:
        'Wind', ... todo to be added.

    Returns
    -------
    prepared_df : pd.DataFrame
        Prepared data. todo form

    """
    if category == 'Wind':  # todo: add 'name' column of name matching from Ludwig!!!
        mastr_data.rename(columns={
            'Nabenhoehe': 'hub_height', 'Rotordurchmesser': 'rotor_diameter',
            # 'HerstellerName', 'Einheitart', 'Einheittyp', 'Technologie',
            'Typenbezeichnung': 'turbine_type',
            # 'Laengengrad': 'lon', 'Breitengrad': 'lat',
            'Inbetriebnahmedatum': 'commissioning_date',
            'DatumEndgueltigeStilllegung': 'decommissioning_date',
            'DatumBeginnVoruebergehendeStilllegung': 'temporary_decom_date',
            'DatumWiederaufnahmeBetrieb': 'resumption_date',
            'InstallierteLeistung': 'capacity'
        }, inplace=True)
    #
    date_cols = ('commissioning_date', 'decommissioning_date')
    prepared_df = ppr_tools.prepare_dates(df=mastr_data, date_cols=date_cols,
                                          month=True)
    return prepared_df


def get_mastr_pp_filtered_by_year(energy_source, year):
    r"""
    Loads MaStR power plant data by `energy_source` and `year`.

    Parameters
    ----------
    energy_source : str
        Energy source for which register is loaded.
    year : int
        Year for which the register is filtered. See filter function
        :py:func:`~.power_plant_register_tools.get_pp_by_year`.

    """
    mastr_pp = helper_load_mastr_from_file(category=energy_source)
    prepared_data = prepare_mastr_data(mastr_pp, energy_source)
    filtered_register = ppr_tools.get_pp_by_year(year=year,
                                                 register=prepared_data)
    filtered_register = ppr_tools.remove_pp_with_missing_coordinates(
        register=filtered_register, category=energy_source,
        register_name='MaStR')
    # prepare turbine types
    # find turbine_types without power curve in oedb turbine_library
    df = get_turbine_types(turbine_library='oedb',
                           print_out=False, filter_=True)
    types_with_power_curve = df[df['has_power_curve'] == True]['turbine_type']
    filtered_register['has_power_curve'] = filtered_register[
        'turbine_type'].apply(lambda x: True if x in list(types_with_power_curve) else False)
    # add turbine types by wind zone in new column
    filtered_register = opsd.assign_turbine_data_by_wind_zone(
        filtered_register, turbine_type_col='new_turbine_type',
        hub_height_col='new_hub_height',
        rotor_diameter_col='new_rotor_diameter')
    # exchange nan in 'turbine_type' column with new turbine type (by windzone)
    # and adapt rotor diameter and hub height
    indices = filtered_register['turbine_type'].loc[
        filtered_register['has_power_curve'] == False].index
    filtered_register['turbine_type'].loc[indices] = filtered_register[
        'new_turbine_type'].loc[indices]
    filtered_register['hub_height'].loc[indices] = filtered_register[
        'new_hub_height'].loc[indices]
    filtered_register['rotor_diameter'].loc[indices] = filtered_register[
        'new_rotor_diameter'].loc[indices]
    return filtered_register.drop(['new_turbine_type', 'new_hub_height',
                                   'new_rotor_diameter'], axis=1)


if __name__ == "__main__":
    year = 2012
    cat = 'Wind'
    mastr_pp = get_mastr_pp_filtered_by_year(energy_source='Wind', year=year)
    print(mastr_pp.head())
