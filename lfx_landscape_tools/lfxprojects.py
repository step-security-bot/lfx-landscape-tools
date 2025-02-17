#!/usr/bin/env python3
#
# Copyright this project and it's contributors
# SPDX-License-Identifier: Apache-2.0
#
# encoding=utf8

import logging

# third party modules
import requests
import requests_cache
from urllib.parse import urlparse

from lfx_landscape_tools.members import Members
from lfx_landscape_tools.member import Member
from lfx_landscape_tools.svglogo import SVGLogo
from lfx_landscape_tools.config import Config

class LFXProjects(Members):

    project = '' 
    defaultCrunchbase = 'https://www.crunchbase.com/organization/linux-foundation'
    endpointURL = 'https://api-gw.platform.linuxfoundation.org/project-service/v1/public/projects?$filter=parentSlug%20eq%20{}&pageSize=2000&orderBy=name'
    singleSlugEndpointUrl = 'https://api-gw.platform.linuxfoundation.org/project-service/v1/public/projects?slug={slug}' 
    calendarUrl = 'https://zoom-lfx.platform.linuxfoundation.org/meetings/{slug}'
    icalUrl = 'https://webcal.prod.itx.linuxfoundation.org/lfx/{project_id}'
    lfxinsightsUrl = "https://insights.lfx.linuxfoundation.org/foundation/{parent_slug}/overview?project={slug}"
    artworkRepoUrl = None

    defaultCategory = ''
    defaultSubcategory = ''

    activeOnly = True
    addTechnologySector = True
    addIndustrySector = True
    addPMOManagedStatus = True
    addParentProject = True

    def processConfig(self, config: type[Config]):
        self.project = config.slug
        self.addTechnologySector = config.projectsAddTechnologySector
        self.addIndustrySector = config.projectsAddIndustrySector
        self.addPMOManagedStatus = config.projectsAddPMOManagedStatus
        self.addParentProject = config.projectsAddParentProject
        self.defaultCrunchbase = config.projectsDefaultCrunchbase
        self.artworkRepoUrl = config.artworkRepoUrl
        self.projectsFilterByParentSlug = config.projectsFilterByParentSlug

    def loadData(self):
        logger = logging.getLogger()
        logger.info("Loading LFX Projects data for {}".format(self.project))

        session = requests_cache.CachedSession()
        with session.get(self.endpointURL.format(self.project if self.projectsFilterByParentSlug else '')) as endpointResponse:
            memberList = endpointResponse.json()
            for record in memberList['Data']:
                if 'Website' in record and self.find(record['Name'],record['Website']):
                    continue
                if self.activeOnly and record['Status'] != 'Active':
                    continue
                if not record['DisplayOnWebsite']:
                    continue
                if record['TestRecord']:
                    continue

                second_path = []
                extra = {}
                member = Member()
                member.membership = 'All'
                member.orgname = record['Name'] if 'Name' in record else None
                logger.info("Found LFX Project '{}'".format(member.orgname))
                extra['slug'] = record['Slug'] if 'Slug' in record else None
                # Let's not include the root project
                if extra['slug'] == self.project:
                    continue
                member.repo_url = record['RepositoryURL'] if 'RepositoryURL' in record else None
                extra['accepted'] = record['StartDate'] if 'StartDate' in record else None 
                member.description = record['Description'] if 'Description' in record else None
                try:
                    member.website = record['Website'] if 'Website' in record else None
                except ValueError as e:
                    logger.info("{} - try to add RepositoryURL instead".format(e))
                    try:
                        member.website = record['RepositoryURL'] if 'RepositoryURL' in record else None
                    except ValueError as e:
                        logger.warning(e)
                if self.addParentProject:
                    parentName = self.lookupParentProjectNameBySlug(record['ParentSlug'] if 'ParentSlug' in record else self.project)
                    if parentName:
                        second_path.append('Project Group / {}'.format(parentName.replace("/",":")))
                try:
                    member.logo = record['ProjectLogo'] if 'ProjectLogo' in record else None
                except ValueError as e:
                    logger.info("{} - will try to create text logo".format(e))
                    member.logo = SVGLogo(name=member.orgname)
                member.crunchbase = record['CrunchBaseUrl'] if 'CrunchbaseUrl' in record else self.defaultCrunchbase
                try:
                    member.twitter = record['Twitter'] if 'Twitter' in record else None
                except (ValueError,KeyError) as e:
                    logger.warning(e)
                if self.addPMOManagedStatus and 'HasProgramManager' in record and record['HasProgramManager']:
                    second_path.append('PMO Managed / All')
                if self.addIndustrySector and 'IndustrySector' in record and record['IndustrySector'] != '':
                    second_path.append('Industry / {}'.format(record['IndustrySector'].replace("/",":")))
                if self.addTechnologySector and 'TechnologySector' in record and record['TechnologySector'] != '':
                    sectors = record['TechnologySector'].split(";")
                    for sector in sectors:
                        second_path.append('Technology Sector / {}'.format(sector.replace("/",":")))
                extra['dev_stats_url'] = self.lfxinsightsUrl.format(parent_slug=record['ParentSlug'] if 'ParentSlug' in record else self.project,slug=extra['slug'])
                extra['calendar_url'] = self.calendarUrl.format(slug=extra['slug']) if 'slug' in extra else None
                extra['ical_url'] = self.icalUrl.format(project_id=record['ProjectID']) if 'ProjectID' in record else None
                if self.artworkRepoUrl:
                    extra['artwork_url'] = self.artworkRepoUrl.format(slug=extra['slug']) if 'slug' in extra and self.artworkRepoUrl else None
                member.extra = extra
                member.second_path = second_path
                self.members.append(member)

    def findBySlug(self, slug):
        for member in self.members:
            if member.extra is not None and 'slug' in member.extra and member.extra['slug'] == slug:
                return member

    def lookupParentProjectNameBySlug(self, slug):
        session = requests_cache.CachedSession()
        if slug:
            with session.get(self.singleSlugEndpointUrl.format(slug=slug)) as endpointResponse:
                parentProject = endpointResponse.json()
                if len(parentProject['Data']) > 0: 
                    return parentProject['Data'][0]["Name"]
                logging.getLogger().warning("Couldn't find project for slug '{}'".format(slug)) 
        
        return False

    def find(self, org, website, membership = None, repo_url = None):
        normalizedorg = self.normalizeCompany(org)
        normalizedwebsite = self.normalizeURL(website)

        members = []
        for member in self.members:
            if membership:
                if ( self.normalizeCompany(member.orgname) == normalizedorg or member.website == normalizedwebsite ) and member.membership == membership:
                    members.append(member)
            elif repo_url:
                if ( self.normalizeCompany(member.orgname) == normalizedorg or member.website == normalizedwebsite or member.repo_url == repo_url):
                    members.append(member)
            else:
                if ( self.normalizeCompany(member.orgname) == normalizedorg or member.website == normalizedwebsite ):
                    members.append(member)
                
        return members

