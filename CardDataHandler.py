# -*- coding:utf-8 -*-

from functools import lru_cache
import requests
from urllib.parse import quote_plus
from Util import process_string, timing
from pyquery import PyQuery as pq
from DatabaseHandler import getClosestTCGCardname
import traceback
import re
import pprint
import difflib

TCG_BASE_URL = 'http://yugiohprices.com/api'
OCG_BASE_URL = 'http://yugioh.wikia.com/api/v1'

toIgnore = ['anime)',
            'manga)',
            'card ruling',
            'card galler',
            'card errata',
            'card tip',
            'card appearance',
            'card trivia',
            'list of',
            'card list',
            'def',
            'atk',
            '(dor)',
            '(cm)',
            '(ddm)',
            '(2)']

BREAK_TOKEN = '__BREAK__'

def sanitiseCardname(cardname):
    return cardname.replace('/', '%2F')

@lru_cache(maxsize=128)
def getOCGCardURL(searchText):
    try:
        endPoint = '/Search/List?query='
        resultLimit = '&limit=5'
        searchResults = requests.get(OCG_BASE_URL + endPoint + searchText + resultLimit)
    except:
        return None
        
    titles = [item['title'].lower() for item in searchResults.json()['items']]

    results = difflib.get_close_matches(searchText.lower(), titles, 1, 0.85)

    if results:
        for item in searchResults.json()['items']:
            if item['title'].lower() == results[0]:
                return item['url']

    return None

@lru_cache(maxsize=128)
def getNonEnglishOCGCardData(searchText):
    try:
        endPoint = '/Search/List?query='
        resultLimit = '&limit=50'
        searchResults = requests.get(OCG_BASE_URL + endPoint + searchText + resultLimit)
        data = searchResults.json()['items']

        cardURL = None

        for result in data:
            if True in [True if word.lower() in result['title'].lower() else False for word in toIgnore]:
                continue
            else:
                cardURL = result['url']
                
                try:
                    cardData = getOCGCardData(cardURL)
                    closest = difflib.get_close_matches(searchText, cardData['languages'], 1, 0.95)[0]
                    
                    if closest:
                        return cardData
                except Exception as e:
                    pass
            
        return None
    except:
        traceback.print_exc()
        return None

@lru_cache(maxsize=128)
def getTCGCardImage(cardName):
    endPoint = '/card_image/'

    try:
        response = requests.get(TCG_BASE_URL + endPoint + quote_plus(cardName))
    except:
        return None
    else:
        response.connection.close()
        if response.ok:
            return response.url

@lru_cache(maxsize=128)
def getTCGCardData(cardName):
    endPoint = '/card_data/'

    try:
        response = requests.get(TCG_BASE_URL + endPoint + quote_plus(cardName))
    except:
        return None
    else:
        response.connection.close()
        if response.ok:
            json = response.json()
            if json.get('status', '') == 'success':
                json['data']['image'] = getTCGCardImage(cardName);
                return json['data']

def getOCGCardData(url):
    try:
        html = requests.get(url)
        ocg = pq(html.text)

        card = ocg('.cardtable')
        statuses = ocg('.cardtablestatuses')

        data = {
            'image': (card.find('td.cardtable-cardimage').eq(0)
                      .find('img').eq(0).attr('src')),
            'name': (card.find('tr.cardtablerow td.cardtablerowdata').eq(0).text()),
            'type': ('trap' if card.find('img[alt="TRAP"]') else
                     ('spell' if card.find('img[alt="SPELL"]') else
                      ('monster' if card.find('th a[title="Type"]') else
                       'other'))),
            'status_advanced': (statuses.find('th a[title="Advanced Format"]')
                                .eq(0).parents('th').next().text()),
            'status_traditional': (
                statuses.find('th a[title="Traditional Format"]').eq(0)
                .parents('th').next().text())
        }

        data['languages'] = []

        romajiCandidates = card.find('tr.cardtablerow th.cardtablerowheader')

        for candidate in romajiCandidates.items():
            if 'rōmaji' in candidate.text():
                data['languages'].append(candidate.parents('tr').find('td').text())

        try:
            languages = card.find('tr.cardtablerow td.cardtablerowdata span')
            for language in languages.items():
                data['languages'].append(language.text())  
        except Exception as e:
            print(e)


        description_element = (card.find('td table table').eq(0).find('tr').eq(2).find('td').eq(0))
        description_element.html(re.sub(r'<br ?/?>', BREAK_TOKEN, description_element.html()))
        description_element.html(re.sub(r'<a href=[^>]+>', '', description_element.html()))
        description_element.html(re.sub(r'</a>', '', description_element.html()))
        
        data['description'] = process_string(description_element.text())
     
        data['description'] = data['description'].replace(BREAK_TOKEN, '\n')

        try:
            data['number'] = process_string(card.find('th a[title="Card Number"]')
                                            .eq(0).parents('tr').eq(0).find('td a')
                                            .eq(0).text())
        except:
            data['number'] = ''
     
        if (data['type'] == 'monster'):
            data['monster_attribute'] = (card.find('th a[title="Attribute"]')
                                         .eq(0).parents('tr').eq(0)
                                         .find('td a').eq(0).text())
     
            try:
                data['monster_level'] = int(process_string(
                    card.find('th a[title="Level"]').eq(0).parents('tr').eq(0)
                    .find('td a').eq(0).text()))
            except:
                data['monster_level'] = int(process_string(
                    card.find('th a[title="Rank"]').eq(0).parents('tr').eq(0)
                    .find('td a').eq(0).text()))
     
            atk_def = (card.find('th a[title="ATK"]').eq(0)
                       .parents('tr').eq(0).find('td').eq(0).text()).split('/')
     
            data['monster_attack'] = process_string(atk_def[0])
            data['monster_defense'] = process_string(atk_def[1])
     
            data['monster_types'] = (process_string(
                card.find('th a[title="Type"]').eq(0).parents('tr').eq(0)
                .find('td').eq(0).text())).split('/')
     
        elif (data['type'] == 'spell' or data['type'] == 'trap'):
            data['spell_trap_property'] = (
                card.find('th a[title="Property"]').eq(0).parents('tr').eq(0)
                .find('td a').eq(0).text())

        if (data['type'] == 'monster'):
            for i, m_type in enumerate(data['monster_types']):
                data['monster_types'][i] = data['monster_types'][i].strip()

        return data
        
    except:
        return None

def getPricesURL(cardName):
    return "http://yugiohprices.com/card_price?name=" + cardName.replace(" ", "+")

def getWikiaURL(cardName):
    return "http://yugioh.wikia.com/wiki/" + cardName.replace(" ", "_")

def formatTCGData(data):
    try:
        formatted = {}
        
        formatted['name'] = data['name']
        formatted['wikia'] = getWikiaURL(data['name'])
        formatted['pricedata'] = getPricesURL(data['name'])
        formatted['image'] = data['image']
        formatted['text'] = re.sub('<!--(.*?)-->', '', data['text'].replace('\n\n', '  \n'))
        formatted['cardtype'] = data['card_type']
        
        if formatted['cardtype'].lower() == 'monster':
            formatted['attribute'] = data['family'].upper()
            formatted['types'] = data['type'].split('/')

            formatted['level'] = data['level']
            formatted['att'] = data['atk']
            formatted['def'] = data['def']

            if 'link' in ' '.join(str(i[1]).lower() for i in enumerate(formatted['types'])):
                formatted['leveltype'] = None
                formatted['level'] = None
                formatted['def'] = None
            elif 'xyz' in ' '.join(str(i[1]).lower() for i in enumerate(formatted['types'])):
                formatted['leveltype'] = 'Rank'
            else:
                formatted['leveltype'] = 'Level'
        else:
            formatted['property'] = data['property']

        return formatted
    except Exception as e:
        return None

def formatOCGData(data):
    try:
        formatted = {}
        
        formatted['name'] = data['name']
        formatted['wikia'] = getWikiaURL(data['name'])
        formatted['pricedata'] = None
        formatted['image'] = data['image']
        formatted['text'] = data['description'].replace('\n', '  \n')
        formatted['cardtype'] = data['type']
        
        if formatted['cardtype'].lower() == 'monster':
            formatted['attribute'] = data['monster_attribute'].upper()
            formatted['types'] = data['monster_types']

            formatted['level'] = data['monster_level']
            formatted['att'] = data['monster_attack']
            formatted['def'] = data['monster_defense']

            if 'link' in ' '.join(str(i[1]).lower() for i in enumerate(formatted['types'])):
                formatted['leveltype'] = None
                formatted['level'] = None
                formatted['def'] = None
            elif 'xyz' in ' '.join(str(i[1]).lower() for i in enumerate(formatted['types'])):
                formatted['leveltype'] = 'Rank'
            else:
                formatted['leveltype'] = 'Level'
        else:
            formatted['property'] = data['spell_trap_property']

        return formatted
    except Exception as e:
        return None

def getCardData(searchText):
    try:
        print('Searching for: ' + searchText)
        
        cardName = getClosestTCGCardname(searchText)
        
        if (cardName): #TCG
            tcgData = getTCGCardData(sanitiseCardname(cardName))

            formattedData = formatTCGData(tcgData)

            if formattedData:
                print("(TCG) Found: " + tcgData['name'])
            else:
                print ("Card not found.")
                
            return formattedData
        else: #OCG
            wikiURL = getOCGCardURL(searchText)
            if (wikiURL):
                ocgData = getOCGCardData(wikiURL)

                formattedData = formatOCGData(ocgData)

                if formattedData:
                    print("(OCG) Found: " + ocgData['name'])
                else:
                    lData = getNonEnglishOCGCardData(searchText)
                    lFormattedData = formatOCGData(lData)

                    if lFormattedData:
                        print("(OCG-L) Found: " + lData['name'])
                    else:
                        print ("Card not found.")

                    return lFormattedData

                return formattedData
            else:
                lData = getNonEnglishOCGCardData(searchText)
                lFormattedData = formatOCGData(lData)

                if lFormattedData:
                    print("(OCG-L) Found: " + lData['name'])
                else:
                    print ("Card not found.")

                return lFormattedData
    except:
        traceback.print_exc()
        return None
