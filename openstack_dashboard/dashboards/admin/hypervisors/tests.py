# Copyright 2013 B1 Systems GmbH
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.urls import reverse

from openstack_dashboard import api
from openstack_dashboard.test import helpers as test


class HypervisorViewTest(test.BaseAdminViewTests):
    @test.create_mocks({api.nova: ['hypervisor_list',
                                   'hypervisor_stats',
                                   'service_list']})
    def test_index(self):
        hypervisors = self.hypervisors.list()
        compute_services = [service for service in self.services.list()
                            if service.binary == 'nova-compute']
        failed_builds = {}
        for index, hypervisor in enumerate(hypervisors):
            hypervisor.failed_builds = index + 1
            failed_builds[hypervisor.hypervisor_hostname] = index + 1
        self.mock_hypervisor_list.return_value = hypervisors
        self.mock_hypervisor_stats.return_value = self.hypervisors.stats
        self.mock_service_list.return_value = compute_services

        res = self.client.get(reverse('horizon:admin:hypervisors:index'))
        self.assertTemplateUsed(res, 'admin/hypervisors/index.html')

        hypervisors_tab = res.context['tab_group'].get_tab('hypervisor')
        self.assertCountEqual(hypervisors_tab._tables['hypervisors'].data,
                              hypervisors)
        for hypervisor in hypervisors_tab._tables['hypervisors'].data:
            self.assertEqual(
                failed_builds[hypervisor.hypervisor_hostname],
                hypervisor.failed_builds)

        host_tab = res.context['tab_group'].get_tab('compute_host')
        host_table = host_tab._tables['compute_host']
        self.assertCountEqual(host_table.data, compute_services)
        for service in host_table.data:
            self.assertEqual(failed_builds.get(service.host, 0),
                             service.failed_builds)

        actions_host_up = [action.name for action in
                           host_table.get_row_actions(host_table.data[0])]
        self.assertEqual(['disable', 'reset_failed_builds'],
                         actions_host_up)

        actions_host_down = [action.name for action in
                             host_table.get_row_actions(host_table.data[1])]
        self.assertEqual(['evacuate', 'disable'], actions_host_down)

        actions_service_disabled = [action.name for action in
                                    host_table.get_row_actions(
                                        host_table.data[2])]
        self.assertEqual(['enable', 'migrate_maintenance',
                          'reset_failed_builds'], actions_service_disabled)

        self.mock_hypervisor_list.assert_called_once_with(
            test.IsHttpRequest())
        self.mock_hypervisor_stats.assert_called_once_with(
            test.IsHttpRequest())
        self.mock_service_list.assert_called_once_with(
            test.IsHttpRequest(), binary='nova-compute')

    @test.create_mocks({api.nova: ['hypervisor_list',
                                   'hypervisor_stats',
                                   'service_list']})
    def test_service_list_unavailable(self):
        # test that error message should be returned when
        # nova.service_list isn't available.

        self.mock_hypervisor_list.return_value = self.hypervisors.list()
        self.mock_hypervisor_stats.return_value = self.hypervisors.stats
        self.mock_service_list.side_effect = self.exceptions.nova

        resp = self.client.get(reverse('horizon:admin:hypervisors:index'))
        self.assertMessageCount(resp, error=2, warning=0)

        self.mock_hypervisor_list.assert_called_once_with(
            test.IsHttpRequest())
        self.mock_hypervisor_stats.assert_called_once_with(
            test.IsHttpRequest())
        self.mock_service_list.assert_called_once_with(
            test.IsHttpRequest(), binary='nova-compute')


class ResetFailedBuildsViewTest(test.BaseAdminViewTests):
    def test_index(self):
        disabled_services = [service for service in self.services.list()
                             if (service.binary == 'nova-compute' and
                                 service.status == 'disabled')]
        disabled_service = disabled_services[0]

        url = reverse('horizon:admin:hypervisors:compute:reset_failed_builds',
                      args=[disabled_service.host])
        res = self.client.get(url)
        template = 'admin/hypervisors/compute/reset_failed_builds.html'
        self.assertTemplateUsed(res, template)

    @test.create_mocks({api.nova: ['reset_failed_builds']})
    def test_successful_post(self):
        disabled_services = [service for service in self.services.list()
                             if (service.binary == 'nova-compute' and
                                 service.status == 'disabled')]
        disabled_service = disabled_services[0]
        self.mock_reset_failed_builds.return_value = True

        url = reverse('horizon:admin:hypervisors:compute:reset_failed_builds',
                      args=[disabled_service.host])
        form_data = {'host': disabled_service.host}

        res = self.client.post(url, form_data)
        dest_url = reverse('horizon:admin:hypervisors:index')
        self.assertNoFormErrors(res)
        self.assertMessageCount(success=1)
        self.assertRedirectsNoFollow(res, dest_url)

        self.mock_reset_failed_builds.assert_called_once_with(
            test.IsHttpRequest(),
            disabled_service.host)

    @test.create_mocks({api.nova: ['reset_failed_builds']})
    def test_failing_nova_call_post(self):
        disabled_services = [service for service in self.services.list()
                             if (service.binary == 'nova-compute' and
                                 service.status == 'disabled')]
        disabled_service = disabled_services[0]

        self.mock_reset_failed_builds.side_effect = self.exceptions.nova

        url = reverse('horizon:admin:hypervisors:compute:reset_failed_builds',
                      args=[disabled_service.host])
        form_data = {'host': disabled_service.host}

        res = self.client.post(url, form_data)
        dest_url = reverse('horizon:admin:hypervisors:index')
        self.assertMessageCount(error=1)
        self.assertRedirectsNoFollow(res, dest_url)

        self.mock_reset_failed_builds.assert_called_once_with(
            test.IsHttpRequest(),
            disabled_service.host)


class HypervisorDetailViewTest(test.BaseAdminViewTests):
    @test.create_mocks({api.nova: ['hypervisor_search']})
    def test_index(self):
        hypervisor = self.hypervisors.first()
        self.mock_hypervisor_search.return_value = [
            hypervisor, self.hypervisors.list()[1]]

        url = reverse('horizon:admin:hypervisors:detail',
                      args=["%s_%s" % (hypervisor.id,
                                       hypervisor.hypervisor_hostname)])
        res = self.client.get(url)
        self.assertTemplateUsed(res, 'admin/hypervisors/detail.html')
        self.assertCountEqual(res.context['table'].data, hypervisor.servers)

        self.mock_hypervisor_search.assert_called_once_with(
            test.IsHttpRequest(), hypervisor.hypervisor_hostname)
