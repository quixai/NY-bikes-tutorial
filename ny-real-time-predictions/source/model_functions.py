import base64
import pickle
import pandas as pd
from datetime import datetime,  timezone, timedelta
from dateutil import tz

def get_saved_model(model_name):
    with open('./MLModels/' + model_name + ".pickle") as file:
        response_binary = base64.b64decode(file.read())
        response_pickle = pickle.loads(response_binary)

    print("Loaded model " + model_name)
    return response_pickle

def get_saved_models():
    ml_model_1h = get_saved_model("ML_1h_Forecast")
    ml_model_1day = get_saved_model("ML_1day_Forecast")
    return ml_model_1h, ml_model_1day

def get_X_predict(current_ny_time, df_weather):    
    
    df_X = pd.DataFrame({'timestamp_ny': [current_ny_time]})
    
    df_X['year'] = df_X['timestamp_ny'].dt.year
    df_X['month'] = df_X['timestamp_ny'].dt.month
    df_X['day'] = df_X['timestamp_ny'].dt.day
    df_X['hour'] = df_X['timestamp_ny'].dt.hour
    df_X['minute'] = df_X['timestamp_ny'].dt.minute
    df_X['dayofweek'] = df_X['timestamp_ny'].dt.dayofweek
    
    df_X['feelslike_temp_c_24'] = float(df_weather.loc[df_weather['TAG__Forecast']=='NextDay', 'feelslike_temp_c'])
    df_X['wind_kph_24'] = float(df_weather.loc[df_weather['TAG__Forecast']=='NextDay', 'wind_kph'])
    df_X['condition_24'] = df_weather.loc[df_weather['TAG__Forecast']=='NextDay', 'condition']

    return df_X

def generate_predictions(current_ny_time, df_bikes, df_weather, ml_model_1h, ml_model_1day):

    df_X = get_X_predict(current_ny_time, df_weather)
    
    cols_1h = ['hour', 'dayofweek']
    cols_1d = ['hour', 'dayofweek', 'wind_kph_24', 'feelslike_temp_c_24']
    
    current_n_bikes = int(df_bikes['total_num_bikes_available'][0])
    
    df_pred_1h = pd.DataFrame({
        'timestamp_ny': [current_ny_time + timedelta(hours=1)], 
        'timestamp_ny_execution': [str(current_ny_time)], 
        'forecast_1h': [current_n_bikes + int(ml_model_1h.predict(df_X[cols_1h]))]})
    
    df_pred_1day = pd.DataFrame({
        'timestamp_ny': [current_ny_time + timedelta(hours=24)], 
        'timestamp_ny_execution': [str(current_ny_time)], 
        'forecast_1d': [current_n_bikes + int(ml_model_1day.predict(df_X[cols_1d]))]})
    
    return df_pred_1h, df_pred_1day

def predict_bikes_availability_and_write_into_streams(df_bikes, df_weather, ml_model_1h, ml_model_1day, stream_0, stream_1, stream_2):

    # If any of the dataframes is empty we cannot predict, so let's check that
    if ((df_bikes.empty) | (df_weather.empty)):
        return

    # Get current time in New York
    current_time = datetime.now(timezone.utc)
    current_ny_time = pd.to_datetime(current_time).astimezone(tz.gettz('America/New_York'))

    # Perform Predictions
    df_pred_1h, df_pred_1day = generate_predictions(current_ny_time, df_bikes, df_weather, ml_model_1h, ml_model_1day)      

    # We write in 3 different streams to define 3 different timestamps
    # Write stream_0: real number of available bikes now
    stream_0.parameters.buffer.add_timestamp(current_ny_time.to_pydatetime()) \
        .add_value('timestamp_ny_execution', str(current_ny_time.to_pydatetime())) \
        .add_value('real_n_bikes', df_bikes.loc[0, 'total_num_bikes_available']) \
        .write()

    # Write stream_1: 1 hour ahead prediction
    stream_1.parameters.buffer.add_timestamp(df_pred_1h.loc[0,'timestamp_ny']) \
        .add_value('timestamp_ny_execution', df_pred_1h.loc[0,'timestamp_ny_execution']) \
        .add_value('forecast_1h', df_pred_1h.loc[0,'forecast_1h']) \
        .write()
    
    # Write stream_2: 1 day ahead prediction
    stream_2.parameters.buffer.add_timestamp(df_pred_1day.loc[0,'timestamp_ny']) \
        .add_value('timestamp_ny_execution', df_pred_1day.loc[0,'timestamp_ny_execution']) \
        .add_value('forecast_1d', df_pred_1day.loc[0,'forecast_1d']) \
        .write()

    # Print some predictions data
    print('NY time:', current_ny_time)
    print('Current n bikes:', int(df_bikes.loc[0, 'total_num_bikes_available']), 'Forecast 1h:', df_pred_1h.loc[0,'forecast_1h'], 'Forecast 1 day:',  df_pred_1day.loc[0,'forecast_1d'])