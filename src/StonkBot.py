import os
import random
import pymongo
import datetime
import seaborn as sns
import matplotlib as plt

from discord.ext import commands
from discord import File
from pandas import DataFrame
from discord import Embed
from dotenv import load_dotenv

mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
db = mongo_client["stonk_bot"]
usercollection = db["users"]
marketcollection = db["market"]
askcollection = db['ask']
bidcollection = db['bid']
tradecollection = db['trade']
statuscollection = db['status']

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix='!')

if len(list(statuscollection.find())) != 1:
    statuscollection.drop()
    statuscollection.insert_one({'closed':True})

def is_closed():
    return statuscollection.find_one()['closed']    

def get_combined_stocks_of_user_with_id(id):
    asks = askcollection.find({"seller_id": id})
    held = usercollection.find_one({"id": id})['stocks']

    combined = {}

    for ask in asks:
        combined[ask['short']] = combined.get(ask['short'], 0) + ask['amount']

    for short in held:
        combined[short] = combined.get(short, 0) + held[short]

    return combined


@bot.command(name='join', help='join the stock market')
async def join(ctx):
    user_id = ctx.author.id
    user_name = ctx.author.name

    user_info = usercollection.find_one({"id": user_id})

    if user_info is not None:
        await ctx.send("you already have joined")
        return

    user_info = {'id': user_id, 'balance': 100, 'name': user_name, 'stocks': {}, 'last_time_malocht': datetime.datetime.utcnow() - datetime.timedelta(hours=12)}
    usercollection.insert_one(user_info)

    await ctx.send("joined")

@bot.command(name='malochen', help='malochen gehen')
async def malochen(ctx):
    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    if user_info['last_time_malocht'] + datetime.timedelta(hours=12) > datetime.datetime.utcnow():
        since_last = datetime.datetime.utcnow() - user_info['last_time_malocht']
        await ctx.send(f"du hast in den letzten 12 stunden schon malocht since last: {since_last}")
        return

    new_money= user_info['balance'] + 200.0

    usercollection.update_one({"id": user_id}, { "$set": {"balance": new_money, "last_time_malocht":  datetime.datetime.utcnow()}})

    await ctx.send("maloche maloche maloche")

@bot.command(name='balance', help='shows your balance')
async def balance(ctx):
    user_id = ctx.author.id

    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    response = f"```Your balance is: {('%.2f' % user_info['balance'])} Fobicoins\n\n" +  "{:<10} {:<10}".format("stock", "amount")

    user_stocks = get_combined_stocks_of_user_with_id(user_id)

    for stock in user_stocks:
        response = response + "\n{:<10} {:<10}".format(stock, user_stocks[stock])

    await ctx.send(response+ "```")

@bot.command(name='market', help='shows the market')
async def market(ctx):
    market = marketcollection.find()

    outstring = "```{:<10} {:<20} {:<10} {:<10} {:<10} {:<10} {:<10} {:<10}".format("shorthand", "name", "shares", "self_held", "last_price", "cap", "balance", "div")

    for stonk in market:
        outstring = outstring + "\n{:<10} {:<20} {:<10} {:<10} {:<10} {:<10} {:<10} {:<10}".format(stonk['short'], stonk['name'], stonk['shares'], stonk['self_held'], stonk['last_price'], '%.2f' % ((int(stonk['shares'])-int(stonk['self_held'])) * float(stonk['last_price'])), "%.2f" % stonk['balance'], stonk['div'])

    await ctx.send(outstring+ "```")

@bot.command(name='top', help='shows top 10 players')
async def overview(ctx):
    top_ten = usercollection.find().sort("balance", -1).limit(10)
    market = marketcollection.find()
    marketPrices= {}

    for stock in market:
        marketPrices[stock['short']] = stock['last_price']

    outstring = "```{:<15} {:<15} {:<15} {:<15}".format("name", "balance", "net_worth", "car")

    for player in top_ten:
        net_worth = float(player['balance'])
        player_stocks = get_combined_stocks_of_user_with_id(player['id'])
        for stock_key in player_stocks:
            net_worth = net_worth + float(player_stocks[stock_key]) * float(marketPrices[stock_key])

        outstring = outstring + "\n{:<15} {:<15} {:<15} {:<15}".format(player['name'], "%.2f" % player['balance'], "%.2f" % net_worth, player.get('car', "None"))
        

    await ctx.send(outstring+ "```")

@bot.command(name='info', help='get info on a specific stock')
async def info(ctx, short=None):
    if short is None:
        await ctx.send("please provide a short hand")
        return

    stock = marketcollection.find_one({"short": short})

    if stock is None:
        await ctx.send("i really dont know this shorthand")
        return

    asks = askcollection.find({"short": short}).sort("price_per_stock")

    outstring = "```asks:\n{:<15} {:<15} {:<15}".format("seller", "amount", "price_per_stock")

    for ask in asks:
        outstring = outstring + "\n{:<15} {:<15} {:<15}".format(ask['seller_name'], ask['amount'], ask['price_per_stock'])

    bids = bidcollection.find({"short": short}).sort("price_per_stock", -1)

    outstring = outstring + "\n\nbids:\n{:<15} {:<15} {:<15}".format("buyer", "amount", "price_per_stock")

    for bid in bids:
        outstring = outstring + "\n{:<15} {:<15} {:<15}".format(bid['buyer_name'], bid['amount'], bid['price_per_stock'])

    await ctx.send(outstring+ "```")

    trades = DataFrame(list(tradecollection.find({"short": short}).sort("when")))

    if len(trades) < 1:
        return

    plot = sns.lineplot(x="when", y="price_per_stock", data=trades)
    plot.get_figure().savefig("out.png")
    plt.pyplot.close(plot.get_figure())

    await ctx.send(file=File("out.png"))
    os.remove("out.png")

@bot.command(name='ask', help='create a sell order')
async def ask(ctx, short=None, amount=None, price_per_stock = None):
    if is_closed():
        await ctx.send("market is closed")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    if short is None or amount is None:
        await ctx.send("Usage: !ask <short> <amount> <price_per_stock>")
        return

    stock = marketcollection.find_one({"short": short})

    if stock is None:
        await ctx.send("i really dont know this shorthand")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if short not in user_info['stocks']:
        await ctx.send(f"you dont even have any {short}")
        return

    amount_of_stocks = int(user_info['stocks'][short])

    if amount_of_stocks < int(amount):
        await ctx.send(f"you dont even have {amount} {short}")
        return

    user_info['stocks'][short] = amount_of_stocks - int(amount)
    usercollection.update_one({"id": user_id}, { "$set": {"stocks": user_info['stocks']}})

    ask = {"seller_id": user_id, "seller_name": user_info['name'], "short": short, "amount": int(amount), "price_per_stock": price_per_stock}

    bids = bidcollection.find({"short": short}).sort("price_per_stock", -1)

    for bid in bids:
        if float(ask['price_per_stock']) <= float(bid['price_per_stock']):
            buy_ask(ask, bid)
            if bid['amount'] == 0:
                bidcollection.delete_one({"_id": bid['_id']})
            else:
                bidcollection.update_one({"_id": bid['_id']}, { "$set": {"amount": bid['amount']}})
        else:    
            break
        if ask['amount'] == 0 :
            break

    if ask['amount'] == 0:
          await ctx.send("ask resolved")
          return

    askcollection.insert_one(ask)
    await ctx.send("ask placed")

def buy_ask(ask, bid):
    if bid['buyer_id'] == ask['seller_id']:
        return

    bid_amount = int(bid['amount'])
    ask_amount = int(ask['amount'])

    ask['amount'] = max(0, ask_amount - bid_amount)
    bid['amount'] = max(0, bid_amount - ask_amount)  

    amount_sold = ask_amount - int(ask['amount'])

    if ask['price_per_stock'] < bid['price_per_stock']:
        price_per_stock = float(bid['price_per_stock'])
    else:
        price_per_stock = float(ask['price_per_stock'])

    money_to_pay = price_per_stock * amount_sold
  
    tradecollection.insert_one({"short": ask['short'], "amount_sold": amount_sold, "price_per_stock": price_per_stock, "when": datetime.datetime.utcnow()})
    marketcollection.update_one({"short": ask['short']}, { "$set": {"last_price": price_per_stock}})

    if 'seller_id' in ask:
        usercollection.update_one({"id": ask['seller_id']}, { "$inc": {"balance": money_to_pay}})

    usercollection.update_one({"id": bid['buyer_id']}, { "$inc": {"balance": -money_to_pay}})

    buyer_info = usercollection.find_one({"id": bid['buyer_id']})
    current_amount = buyer_info['stocks'].get(bid['short'], 0)
    buyer_info['stocks'][bid['short']] = current_amount + amount_sold

    usercollection.update_one({"id": bid['buyer_id']}, { "$set": {"stocks": buyer_info['stocks']}})

@bot.command(name='bid', help='create a buy order')
async def bid(ctx, short=None, amount=None, price_per_stock = None):
    if is_closed():
        await ctx.send("market is closed")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    if short is None or amount is None:
        await ctx.send("Usage: !bid <short> <amount> <price_per_stock>")
        return

    stock = marketcollection.find_one({"short": short})

    if stock is None:
        await ctx.send("i really dont know this shorthand")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    total_price = int(amount) * float(price_per_stock)

    if(user_info['balance']< total_price):
        await ctx.send(f"nice try, but youre missing {total_price- user_info['balance']} fobicoins")
        return

    bid = {"buyer_id": user_id, "buyer_name": user_info['name'], "short": short, "amount": amount, "price_per_stock": price_per_stock}

    current_asks = askcollection.find({"short": short}).sort("price_per_stock")

    for ask in current_asks:
        if float(ask['price_per_stock']) <= float(bid['price_per_stock']):
            buy_ask(ask, bid)
            if ask['amount'] == 0:
                askcollection.delete_one({"_id": ask['_id']})
            else:
                askcollection.update_one({"_id": ask['_id']}, { "$set": {"amount": ask['amount']}})
        if bid['amount'] == 0 :
            break

    if bid['amount'] == 0:
        await ctx.send("bid resolved")
        return

    bidcollection.insert_one(bid)
    await ctx.send("bid placed")

@bot.command(name='cancelbid', help='cancel all bids on a stock')
async def cancelbid(ctx, short=None):
    if is_closed():
        await ctx.send("market is closed")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    if short is None:
        await ctx.send("Usage: !cancelbid <short>")
        return

    bidcollection.delete_many({"buyer_id": user_id, "short": short})
    
    await ctx.send("done")

@bot.command(name='cancelask', help='cancel all asks on a stock')
async def cancelask(ctx, short=None):
    if is_closed():
        await ctx.send("market is closed")
        return

    user_id = ctx.author.id
    user_info = usercollection.find_one({"id": user_id})

    if user_info is None:
        await ctx.send("i dont know you you have to !join first")
        return

    if short is None:
        await ctx.send("Usage: !cancelask <short>")
        return

    asks = askcollection.find({"seller_id": user_id, "short": short})
    user_stocks = user_info['stocks']

    for ask in asks:
        user_stocks[short] = user_stocks[short] + ask['amount']
        askcollection.delete_one({"_id": ask['_id']})

    usercollection.update_one({"id": user_id}, { "$set": {"stocks": user_stocks}})

    await ctx.send("done")

@bot.command(name='closemarket')
@commands.has_role('stonkbot')
async def closemarket(ctx):
    statuscollection.drop()
    statuscollection.insert_one({'closed':True})
    await ctx.send(":bell::bell::bell: market closed :bell::bell::bell:")

@bot.command(name='openmarket')
@commands.has_role('stonkbot')
async def openmarket(ctx):
    statuscollection.drop()
    statuscollection.insert_one({'closed':False})
    await ctx.send(":bell::bell::bell: market opened :bell::bell::bell:")

    stonks = marketcollection.find()
    users = usercollection.find()

    outstring = "```stock performance:\n{:<15} {:<15} {:<15}".format("short", "profit", "dividend")

    for stonk in stonks:
        change = float(stonk['balance']) * random.uniform(-0.15, 0.15 * float(stonk['performance']))
        dividend_per_share = 0.0

        if change > 0:
            traded_shares = int(stonk['shares']) - int(stonk['self_held'])
            dividend_per_share = change * float(stonk['div']) / traded_shares
            change = change - dividend_per_share * traded_shares
        
        marketcollection.update_one({"short": stonk['short']}, { "$inc": {"balance": change}})
        outstring = outstring + "\n{:<15} {:<15} {:<15}".format(stonk['short'], "%.2f" % change, "%.2f" % dividend_per_share)

        for user in users:
            user_stocks = get_combined_stocks_of_user_with_id(user['id'])
            number_of_stocks = int(user_stocks.get(stonk['short'], 0))
            if number_of_stocks > 0:
                usercollection.update_one({"id": user['id']}, { "$inc": {"balance": number_of_stocks * dividend_per_share}})

    await ctx.send(outstring+ "```")

bot.run(TOKEN)