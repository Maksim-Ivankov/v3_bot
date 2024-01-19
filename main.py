# тестовый депозит, реальные данные
# точки находит достаточно тупо на 1,5 таймфреймах. На больших не проверял, хотя следовало бы. А почему бы и нет. 
# доделаю бота и запущу на тестовом сервере на пару дней.

import matplotlib.pyplot as plt
import pandas as pd
import requests
import websockets
import asyncio
import json
import time
from time import gmtime, strftime
import numpy as np
import statsmodels.api as sm
import warnings
from binance.um_futures import UMFutures
from config import TG_API,TG_ID,TG_NAME_BOT,key,secret
warnings.filterwarnings("ignore")
import os
import glob

symbol = '' # по какой паре торгуем
width = 0.6 # Ширина тела свечи
width2 = 0.05 # Ширина хвоста, шпиля
timeout = time.time() + 60*60*12  # время, которое будет работать скрипт
TF = '15m' # таймфрейм
wait_time = 15 # сколько минут ждать для обновления цены с биржи
TP = 0.002 # Тейк профит, процент
SL = 0.002 # Стоп лосс, процент
DEPO = 100 # Депозит
Leverage = 20 # торговое плечо
DEPOSIT = DEPO # лень переписывать
open_position = False # флаг, стоим в позиции или нет
commission_maker = 0.001 # комиссия а вход
comission_taker = 0.002 # комиссия на выхд
name_bot = 'V_3' # версия бота для сообщений в тг
volume = 30 # сколько свечей получить при запросе к бирже
canal_max = 0.85 # Верх канала
canal_min = 0.15 # Низ канала
corner_short = 10 # Угол наклона шорт
corner_long = 10 # Угол наклона лонг
candle_coin_min = 200000 # объем торгов за свечку
candle_coin_max = 500000 # объем торгов за свечку
rigime_gen_df = 2 # 1 - сгенерировать датафреймы в файл, 2 - получить датафреймы из файла
mydir_worker = 'dev/df/worker/'
mydir_5min = 'dev/df/5min/'

data_value = 'Настройки бота:\nТаймфрейм - '+str(TF)+'\nТейк профит - '+str(TP)+'\nСтоп лосс - '+str(SL)+'\nНачальный депозит - '+str(DEPO)+'\nПлечо - '+str(Leverage)+'\nНазвание бота - '+str(name_bot)+'\nВерх канала - '+str(canal_max)+'\nНиз канала - '+str(canal_min)+'\nУгол наклона шорт - '+str(corner_short)+'\nУгол наклона лонг - '+str(corner_long)+'\nОбъем торгов мин - '+str(candle_coin_min)+'\nОбъём торгов макс - '+str(candle_coin_max)

day_trade = round((wait_time*volume)/(60*24),1)
open_sl = False # флаг на открытые позиции
price_trade = 0
signal_trade = ''
coin_trade = ''
value_trade = 0
coin_mas_10 = []
profit = 0
loss = 0
commission = 0
data_numbers = []
count_long_take = 0
count_short_take = 0
count_long_loss = 0
count_short_loss = 0

client = UMFutures(key=key, secret=secret)

name_log = name_bot+'_log.txt'
def logger(msg):
    f = open(name_log,'a',encoding='utf-8')
    f.write('\n'+time.strftime("%d.%m.%Y | %H:%M:%S | ", time.localtime())+msg)
    f.close()
logger('------------------------------------------------------------')
logger('Бот запущен в работу')
logger(data_value)

# Получите последние n свечей по n минут для торговой пары, обрабатываем и записывае данные в датафрейм
def get_futures_klines(symbol,TF,volume):
    x = requests.get('https://binance.com/fapi/v1/klines?symbol='+symbol.lower()+'&limit='+str(volume)+'&interval='+TF)
    df=pd.DataFrame(x.json())
    df.columns=['open_time','open','high','low','close','volume','close_time','d1','d2','d3','d4','d5']
    df=df.drop(['d1','d2','d3','d4','d5'],axis=1)
    df['open']=df['open'].astype(float)
    df['high']=df['high'].astype(float)
    df['low']=df['low'].astype(float)
    df['close']=df['close'].astype(float)
    df['volume']=df['volume'].astype(float)
    return(df) # возвращаем датафрейм с подготовленными данными

# Получаем активные монеты на бирже
def get_top_coin():
    data = client.ticker_24hr_price_change()
    change={}
    coin={}
    coin_mas = []
    coin_mas_10 = []
    for i in data:
        change[i['symbol']] = float(i['priceChangePercent'])
    coin = dict(sorted(change.items(), key=lambda item: item[1],reverse=True))
    for key in coin:
        coin_mas.append(key)
    for x,result in enumerate(coin_mas):
        if x==10:
            break
        coin_mas_10.append(result)
    return coin_mas_10

coin_mas_10 = get_top_coin()
# определяем размер позиции, на которую должны зайти
def get_trade_volume(get_symbol_price):
    volume = round(float(DEPOSIT)*float(Leverage)/float(get_symbol_price))
    return float(volume)

# отправляет сообщение в бота и принтует в консоль
def prt(message):
    # print(message)
    url = 'https://api.telegram.org/bot{}/sendMessage'.format(TG_API)
    data = {
        'chat_id': TG_ID,
        'text': message
    }
    response = requests.post(url, data=data)

prt(f'Робот {name_bot} запущен!\n{data_value}')




# -------------------------------------- ИНДИКАТОРЫ --------------------------------------

# Индикатор истинного диапазона и среднего значения истинного диапазона
def indATR(source_DF,n):
    df = source_DF.copy()
    df['H-L']=abs(df['high']-df['low'])
    df['H-PC']=abs(df['high']-df['close'].shift(1))
    df['L-PC']=abs(df['low']-df['close'].shift(1))
    df['TR']=df[['H-L','H-PC','L-PC']].max(axis=1,skipna=False)
    df['ATR'] = df['TR'].rolling(n).mean()
    df_temp = df.drop(['H-L','H-PC','L-PC'],axis=1)
    return df_temp

# Определяем наклон ценовой линии
def indSlope(series,n):
    array_sl = [j*0 for j in range(n-1)]
    for j in range(n,len(series)+1):
        y = series[j-n:j]
        x = np.array(range(n))
        x_sc = (x - x.min())/(x.max() - x.min())
        y_sc = (y - y.min())/(y.max() - y.min())
        x_sc = sm.add_constant(x_sc)
        model = sm.OLS(y_sc,x_sc)
        results = model.fit()
        array_sl.append(results.params[-1])
    slope_angle = (np.rad2deg(np.arctan(np.array(array_sl))))
    return np.array(slope_angle)

# найти локальный минимум
def isLCC(DF,i):
    df=DF.copy()
    LCC=0
    if df['close'][i]<=df['close'][i+1] and df['close'][i]<=df['close'][i-1] and df['close'][i+1]>df['close'][i-1]:
        #найдено Дно
        LCC = i-1
    return LCC

# найти локальный максимум
def isHCC(DF,i):
    df=DF.copy()
    HCC=0
    if df['close'][i]>=df['close'][i+1] and df['close'][i]>=df['close'][i-1] and df['close'][i+1]<df['close'][i-1]:
        #найдена вершина
        HCC = i
    return HCC

# сгенерируйте фрейм данных со всеми необходимыми данными
def PrepareDF(DF):
    ohlc = DF.iloc[:,[0,1,2,3,4,5]]
    ohlc.columns = ["date","open","high","low","close","volume"]
    ohlc=ohlc.set_index('date')
    df = indATR(ohlc,14).reset_index()
    df['slope'] = indSlope(df['close'],5)
    df['channel_max'] = df['high'].rolling(10).max() # определяем верхний уровень канала
    df['channel_min'] = df['low'].rolling(10).min() # определяем нижний уровень канала
    df['position_in_channel'] = (df['close']-df['channel_min']) / (df['channel_max']-df['channel_min']) # сейчас находимся выше середины канала или ниже
    df = df.set_index('date')
    df = df.reset_index()
    return(df)

# -------------------------------------- ИНДИКАТОРЫ --------------------------------------
# -------------------------------------- ТОРГОВЛЯ --------------------------------------

# открывает лонг или шорт
def open_position(trend,value,price):
    global open_sl
    global price_trade
    global signal_trade
    global coin_trade
    global value_trade
    global take_profit_price
    global stop_loss_price
    price_trade = price
    signal_trade = trend
    coin_trade = symbol
    value_trade = value
    open_sl = True
    take_profit_price = get_take_profit(trend,price_trade) # получаем цену тэйк профита
    stop_loss_price = get_stop_loss(trend,price_trade) # получаем цену стоп лосса
    print(f'ТЕЙК - {take_profit_price}')
    print(f'СТОП - {stop_loss_price}')
    print(f'Новая сделка. Монета - {symbol} | Зашли в {trend} | Цена входа - {price_trade}')
    prt(f'🚀 -----Сделка----- 🚀\nБот - {name_bot}\nМонета - {symbol}\nЗашли в {trend}\nЦена входа - {price_trade}')
    logger(f'Новая сделка. Монета - {symbol} | Зашли в {trend} | Цена входа - {price_trade}')

def get_take_profit(trend,price_trade): # получаем цену тейк профита в зависимости от направления
    if trend == 'long':
        return float(float(price_trade)*(1+float(TP)))
    if trend == 'short':
        return float(float(price_trade)*(1-float(TP)))
def get_stop_loss(trend,price_trade): # получаем цену стоп лосса в зависимости от направления
    if trend == 'long':
        return float(float(price_trade)*(1-float(SL)))
    if trend == 'short':
        return float(float(price_trade)*(1+float(SL)))

# Закрываем сделку
def close_trade(status,procent):
    global DEPO
    global open_sl
    global profit
    global loss
    global commission
    if status == '+': # если закрыли в плюс
        profit = profit + Leverage*DEPO*procent
        commission = commission + Leverage*DEPO*(commission_maker+comission_taker)
        DEPO = DEPO + Leverage*DEPO*procent - Leverage*DEPO*(commission_maker+comission_taker) # обновляем размер депо
        logger(f'Сработал тейк! Закрылись в плюс, депо = {DEPO} Прибыль = {profit} Комиссия = {commission}')
        prt(f'{name_bot} - Сработал тейк!\nЗакрылись в плюс, депо = {DEPO}\nПрибыль = {profit}\nКомиссия = {commission}')
        open_sl = False
    if status == '-': # если закрыли в минус
        loss = loss + Leverage*DEPO*procent
        commission = commission + Leverage*DEPO*(commission_maker+comission_taker)
        DEPO = DEPO - Leverage*DEPO*procent - Leverage*DEPO*(commission_maker+comission_taker) # обновляем размер депо
        logger(f'Сработал стоп! Закрылись в минус, депо = {DEPO} Убыток = {loss} Комиссия = {commission}')
        prt(f'{name_bot} - Сработал стоп!\nЗакрылись в минус, депо = {DEPO}\nУбыток = {loss}\nКомиссия = {commission}')
        open_sl = False

def check_trade(price):
    now_price_trade = price #получаем текущую цену монеты
    global count_long_take
    global count_long_loss
    global count_short_take
    global count_short_loss
    if signal_trade == 'long':
        if float(now_price_trade)>float(take_profit_price):
            close_trade('+',TP)
            count_long_take=count_long_take+1
            return 1
        if float(now_price_trade)<float(stop_loss_price):
            count_long_loss = count_long_loss + 1
            close_trade('-',SL)
            return 1
    if signal_trade == 'short':
        if float(now_price_trade)<float(take_profit_price):
            close_trade('+',TP)
            count_short_take = count_short_take+1
            return 1
        if float(now_price_trade)>float(stop_loss_price):
            count_short_loss = count_short_loss + 1
            close_trade('-',SL)
            return 1
# -------------------------------------- ТОРГОВЛЯ --------------------------------------
# -------------------------------------- СТРАТЕГИЯ --------------------------------------

def check_if_signal(ohlc,index):
    prepared_df = PrepareDF(ohlc)
    signal="нет сигнала" # возвращаемый сигнал, лонг или шорт
    i=index-2 # 99 - текущая свеча, которая не закрыта, 98 - последняя закрытая свеча, нам нужно 97, чтобы проверить, нижняя она или верхняя
    if isHCC(prepared_df,i-1)>0: # если у нас локальный минимум
        if prepared_df['position_in_channel'][i-1]>canal_max: # проверяем, прижаты ли мы к нижней границе канала
            if prepared_df['slope'][i-1]>corner_short: # смотрим, какой у нас наклон графика
                signal='short'
    if isLCC(prepared_df,i-1)>0: # если у нас локальный максимум
        if prepared_df['position_in_channel'][i-1]<canal_min: # проверяем, прижаты ли мы к верхней границе канала
            if prepared_df['slope'][i-1]<corner_long: # смотрим, какой наклон графика
                signal='long'
    return signal
    
# -------------------------------------- СТРАТЕГИЯ --------------------------------------

def get_price_now_coin(symbol):
    key = "https://api.binance.com/api/v3/ticker/price?symbol="+symbol
    data = requests.get(key)   
    data = data.json() 
    price = data['price']
    return price
     
async def websocket_trade():
    url = 'wss://stream.binance.com:9443/stream?streams='+symbol.lower()+'@miniTicker'
    async with websockets.connect(url) as client: #асинхронно открываем соединение, называем его клиентом, после выхода из контекста функции, закрываем соединение
        while True:
            data = json.loads(await client.recv())['data']
            print(data['c'])
            if check_trade(data['c']): # следим за монетой, отрабатываем тп и сл
                break

# -------------------------------------- Перебор по датафрейму --------------------------------------

while True:
    try:     
        sost_trading = 'Депозит = '+str(DEPO)+'| Сделки в плюс принесли '+str(profit)+'| Сделки в минус принесли '+str(loss)+'| На комиссию потратил '+str(commission)
        if open_sl == False:
            for x,result in enumerate(coin_mas_10):
                print(result)
                prices = get_futures_klines(result,TF,volume)
                trend = check_if_signal(prices,volume)
                time.sleep(2) # Интервал в 10 секунд, чтобы бинанс не долбить
                if trend != 'нет сигнала':
                    symbol = result
                    print(f'Монета с сигналом - {symbol}')
                    break
            # trend = 'long'
            # symbol = 'UMAUSDT'
            if trend == "нет сигнала":
                logger(time.strftime("%d.%m.%Y г. %H:%M", time.localtime()) + ' - Нет сигнала')
                time.sleep(wait_time*2) # Двойной интервал, если нет сигнала
            else:
                print(f'Проверка монеты - {symbol}')
                price__now = get_price_now_coin(symbol)
                open_position(trend,get_trade_volume(price__now),price__now) # если есть сигнал и мы не стоим в позиции, то открываем позицию
        if open_sl == True:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(websocket_trade())
        if DEPO < 0:
            logger('Бот слил всё депо! Завершили работу бота')
            logger(sost_trading)
            logger(f'Бот {name_bot} слил всё депо! Завершили работу бота') #
            break
    except KeyboardInterrupt: #
        logger(f'\nСбой в работе {name_bot}. Остановка.') #
        logger(sost_trading)
        logger(f'В плюс закрыли лонгов - {count_long_take}, шортов - {count_short_take}')
        logger(f'В минус закрыли лонгов - {count_long_loss}, шортов - {count_short_loss}')
        prt(sost_trading)
        prt(f'В плюс закрыли лонгов - {count_long_take}, шортов - {count_short_take}')
        prt(f'В минус закрыли лонгов - {count_long_loss}, шортов - {count_short_loss}')
        exit() 


















